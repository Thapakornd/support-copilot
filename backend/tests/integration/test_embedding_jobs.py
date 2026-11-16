from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import uuid4

import psycopg
import pytest
from support_copilot.domain.embedding_job import EmbeddingConfig, OwnershipLost
from support_copilot.infrastructure.postgres.embedding_jobs import (
    PostgresEmbeddingStore,
)


@pytest.fixture
def config(db):
    config = EmbeddingConfig(
        uuid4(), "approved/test", "a" * 40, 3, 128, "passage: ", "query: "
    )
    with psycopg.connect(db) as conn:
        conn.execute(
            "INSERT INTO embedding_models VALUES (%s,'sentence-transformers',%s,%s,3,'cosine',true)",
            (config.model_id, config.model_name, config.model_revision),
        )
    return config


def seed(db, config, count=1):
    with psycopg.connect(db) as conn:
        for i in range(count):
            rev = uuid4()
            conn.execute(
                "INSERT INTO knowledge_documents(document_id,data) VALUES (%s,'{}')",
                (str(i),),
            )
            conn.execute(
                """INSERT INTO knowledge_document_revisions
                (id,document_id,revision_hash,content_hash,title,source_url,source_type,product,
                deployment,version_scope,category_id,topics,content_markdown,excerpt,source_payload,fetched_at)
                VALUES (%s,%s,%s,'hash','Title','https://example.org','documentation','p','d','v',
                'connectivity','{}','# Title\n\nBody','Body','{}',now())""",
                (rev, str(i), str(rev)),
            )
            conn.execute(
                """UPDATE knowledge_documents SET requested_revision_id=%s,
                requested_embedding_config_hash=%s,ingestion_generation=1 WHERE document_id=%s""",
                (rev, config.config_hash, str(i)),
            )
            conn.execute(
                """INSERT INTO embedding_jobs(id,document_id,revision_id,generation,model_id,
                chunker_version,config_hash,config) VALUES (%s,%s,%s,1,%s,%s,%s,%s::jsonb)""",
                (
                    uuid4(),
                    str(i),
                    rev,
                    config.model_id,
                    config.chunker_version,
                    config.config_hash,
                    config.canonical_json(),
                ),
            )


def test_concurrent_claims_and_owner_fencing(db, config):
    seed(db, config, 2)
    store = PostgresEmbeddingStore(db)
    cutoff = store.now()
    with ThreadPoolExecutor(2) as pool:
        jobs = list(
            pool.map(lambda _: store.claim(config.config_hash, cutoff), range(2))
        )
    assert len({job.id for job in jobs}) == 2
    assert store.claim(config.config_hash, cutoff) is None
    stale = replace(jobs[0], claim_token=uuid4())
    assert not store.renew(stale)
    with pytest.raises(OwnershipLost):
        store.fail(stale, "encoding_resource", True)
    assert store.renew(jobs[0])


def test_recovery_rotates_ownership_and_respects_cutoff(db, config):
    seed(db, config, 2)
    store = PostgresEmbeddingStore(db)
    first = store.claim(config.config_hash, store.now())
    second = store.claim(config.config_hash, store.now())
    with psycopg.connect(db) as conn:
        conn.execute(
            "UPDATE embedding_jobs SET lease_expires_at=now()-interval '1 second' WHERE id=%s",
            (first.id,),
        )
    cutoff = store.now()
    recovered = store.recover(cutoff)
    assert recovered.recovered == 1
    again = store.claim(config.config_hash, cutoff)
    assert again.id == first.id and again.claim_token != first.claim_token
    assert not store.renew(first)
    assert store.renew(second)
    assert store.fail(again, "encoding_resource", True) == "pending"
    assert store.claim(config.config_hash, cutoff) is None


def test_constraints_and_registry_immutability(db, config):
    seed(db, config)
    with psycopg.connect(db) as conn, pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("UPDATE embedding_jobs SET status='processing'")
    with (
        psycopg.connect(db) as conn,
        pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
    ):
        conn.execute(
            "UPDATE embedding_models SET dimensions=4 WHERE id=%s", (config.model_id,)
        )


def test_later_lease_expiry_waits_for_next_invocation(db, config):
    from threading import Event

    seed(db, config)
    store = PostgresEmbeddingStore(db)
    job = store.claim(config.config_hash, store.now())
    cutoff = store.now()
    with psycopg.connect(db) as conn:
        conn.execute(
            "UPDATE embedding_jobs SET lease_expires_at=%s+interval '0.02 seconds' WHERE id=%s",
            (cutoff, job.id),
        )
    Event().wait(0.03)
    assert store.recover(cutoff).recovered == 0
    assert store.recover(store.now()).recovered == 1
    again = store.claim(config.config_hash, store.now())
    assert again.claim_token != job.claim_token


def test_failure_transition_rechecks_lease_after_transaction_delay(
    db, config, monkeypatch
):
    from support_copilot.infrastructure.postgres import embedding_jobs

    seed(db, config)
    store = PostgresEmbeddingStore(db)
    job = store.claim(config.config_hash, store.now())
    with psycopg.connect(db) as conn:
        conn.execute(
            "UPDATE embedding_jobs SET lease_expires_at=now()+interval '0.3 seconds' WHERE id=%s",
            (job.id,),
        )
    original = embedding_jobs.lock_owned

    def delayed(conn, claimed):
        result = original(conn, claimed)
        conn.execute("SELECT pg_sleep(0.5)")
        return result

    monkeypatch.setattr(embedding_jobs, "lock_owned", delayed)
    with pytest.raises(OwnershipLost):
        store.fail(job, "encoding_resource", True)
