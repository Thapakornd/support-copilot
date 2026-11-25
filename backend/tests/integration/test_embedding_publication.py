import psycopg
import pytest
from test_embedding_admission import stage

from support_copilot.domain.embedding_job import OwnershipLost, ProcessingError
from support_copilot.infrastructure.postgres.knowledge_repository import (
    KnowledgeRepository,
)


def chunks(text="First"):
    return [
        {
            "chunk_id": "chunk_1",
            "chunk_index": 0,
            "heading_path": ["Help"],
            "text": text,
            "char_count": len(text),
            "oversized": False,
        }
    ]


def publication(db):
    with psycopg.connect(db) as conn:
        return conn.execute(
            "SELECT chunk_set_id FROM retrieval_publications WHERE document_id='doc-1'"
        ).fetchone()


def test_lease_expiring_during_publication_rolls_back(db, config):
    store = KnowledgeRepository(db)
    stage(db)
    store.admit(config, None)
    job = store.claim(config.config_hash, store.now())
    with psycopg.connect(db) as conn:
        conn.execute(
            "UPDATE embedding_jobs SET lease_expires_at=now()+interval '0.3 seconds' WHERE id=%s",
            (job.id,),
        )
        conn.execute("""CREATE FUNCTION slow_publication() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN PERFORM pg_sleep(0.5); RETURN NEW; END $$;
            CREATE TRIGGER slow_publication BEFORE INSERT ON retrieval_publications
            FOR EACH ROW EXECUTE FUNCTION slow_publication()""")
    with pytest.raises(OwnershipLost):
        store.publish(job, chunks(), [[1, 0, 0]])
    assert publication(db) is None


def test_atomic_publication_and_newer_target_fencing(db, config):
    store = KnowledgeRepository(db)
    stage(db)
    store.admit(config, None)
    first = store.claim(config.config_hash, store.now())
    assert store.publish(first, chunks(), [[1, 0, 0]]) == "completed"
    previous = publication(db)
    stage(db, "Second")
    store.admit(config, None)
    second = store.claim(config.config_hash, store.now())
    stage(db, "Third")
    store.admit(config, None)
    assert store.publish(second, chunks("Second"), [[1, 0, 0]]) == "superseded"
    assert publication(db) == previous
    third = store.claim(config.config_hash, store.now())
    assert store.load_snapshot(third)["content_markdown"] == "# Help\n\nThird"
    assert store.publish(third, chunks("Third"), [[0, 1, 0]]) == "completed"
    assert publication(db) != previous


def test_failed_final_transaction_preserves_previous_publication(db, config):
    store = KnowledgeRepository(db)
    stage(db)
    store.admit(config, None)
    first = store.claim(config.config_hash, store.now())
    store.publish(first, chunks(), [[1, 0, 0]])
    previous = publication(db)
    stage(db, "Changed")
    store.admit(config, None)
    second = store.claim(config.config_hash, store.now())
    with psycopg.connect(db) as conn:
        conn.execute("""CREATE FUNCTION reject_publication() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'forced rollback'; END $$;
            CREATE TRIGGER reject_publication BEFORE UPDATE ON retrieval_publications
            FOR EACH ROW EXECUTE FUNCTION reject_publication()""")
    with pytest.raises(psycopg.Error):
        store.publish(second, chunks("Changed"), [[0, 1, 0]])
    assert publication(db) == previous
    with psycopg.connect(db) as conn:
        assert (
            conn.execute(
                "SELECT status FROM embedding_jobs WHERE id=%s", (second.id,)
            ).fetchone()[0]
            == "processing"
        )
        assert (
            conn.execute("SELECT count(*) FROM knowledge_chunk_sets").fetchone()[0] == 1
        )
        conn.execute("DROP TRIGGER reject_publication ON retrieval_publications")
    assert store.publish(second, chunks("Changed"), [[0, 1, 0]]) == "completed"
    with pytest.raises(OwnershipLost):
        store.publish(second, chunks("Changed"), [[0, 1, 0]])


@pytest.mark.parametrize("mutation", ["expire", "deactivate", "invalid_vectors"])
def test_expired_inactive_or_invalid_work_never_publishes(db, config, mutation):
    store = KnowledgeRepository(db)
    stage(db)
    store.admit(config, None)
    job = store.claim(config.config_hash, store.now())
    with psycopg.connect(db) as conn:
        if mutation == "expire":
            conn.execute(
                "UPDATE embedding_jobs SET lease_expires_at=now()-interval '1 second' WHERE id=%s",
                (job.id,),
            )
        elif mutation == "deactivate":
            conn.execute("UPDATE knowledge_documents SET is_active=false")
    if mutation == "deactivate":
        assert store.publish(job, chunks(), [[1, 0, 0]]) == "superseded"
    else:
        with pytest.raises(ProcessingError):
            store.publish(
                job,
                chunks(),
                [[0, 0, 0]] if mutation == "invalid_vectors" else [[1, 0, 0]],
            )
    assert publication(db) is None
