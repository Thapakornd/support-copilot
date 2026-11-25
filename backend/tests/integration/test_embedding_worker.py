from dataclasses import replace
from threading import Event

import psycopg
from test_embedding_admission import stage

from support_copilot.domain.embedding_job import ProcessingError
from support_copilot.infrastructure.embeddings.chunker import TokenAwareChunker
from support_copilot.infrastructure.postgres.knowledge_repository import (
    KnowledgeRepository,
)
from support_copilot.interface.worker.main import run_once


class Encoder:
    def token_count(self, text, *, query=False):
        return len(text) + 2

    def encode_documents(self, texts):
        return [[1.0, 0.0, 0.0] for _ in texts]


def run(store, config, factory=Encoder, **kwargs):
    return run_once(store, factory, TokenAwareChunker(), config, Event(), **kwargs)


def test_recovered_work_is_eligible_owned_elsewhere_exits(db, config):
    store = KnowledgeRepository(db)
    stage(db)
    stage(db, document_id="doc-2")
    store.admit(config, None)
    expired = store.claim(config.config_hash, store.now())
    live = store.claim(config.config_hash, store.now())
    with psycopg.connect(db) as conn:
        conn.execute(
            "UPDATE embedding_jobs SET lease_expires_at=now()-interval '1 second' WHERE id=%s",
            (expired.id,),
        )
    summary = run(store, config)
    assert summary.recovered == 1 and summary.completed == 1
    assert summary.owned_elsewhere == 1 and summary.exit_code == 0
    assert store.renew(live)
    assert not store.renew(expired)


def test_once_ignores_jobs_admitted_after_cutoff(db, config):
    store = KnowledgeRepository(db)
    stage(db)
    store.admit(config, None)

    class Admitting(Encoder):
        def encode_documents(self, texts):
            stage(db, document_id="doc-2")
            store.admit(config, None)
            return super().encode_documents(texts)

    summary = run(store, config, Admitting)
    assert summary.completed == 1 and summary.exit_code == 0
    assert store.claim(config.config_hash, store.now()).document_id == "doc-2"


def test_blocked_configuration_and_cross_config_supersession(db, config):
    store = KnowledgeRepository(db)
    stage(db)
    store.admit(config, None)
    different = replace(config, document_prompt="new: ")
    summary = run(store, different)
    assert summary.blocked == 1 and summary.exit_code == 1
    store.admit(different, None)
    summary = run(store, different)
    assert summary.completed == 1 and summary.superseded == 1
    assert summary.exit_code == 0


def test_backoff_does_not_spin_and_historical_failures_do_not_poison_exit(db, config):
    store = KnowledgeRepository(db)
    stage(db)
    store.admit(config, None)

    class Broken(Encoder):
        def encode_documents(self, texts):
            raise ProcessingError("encoding_resource", retryable=True)

    summary = run(store, config, Broken)
    assert summary.rescheduled == 1 and summary.deferred == 1 and summary.exit_code == 1
    assert run(store, config).exit_code == 0
    with psycopg.connect(db) as conn:
        conn.execute("UPDATE embedding_jobs SET status='failed',finished_at=now()")
    assert run(store, config).exit_code == 0


def test_exhausted_recovery_is_reported_once(db, config):
    store = KnowledgeRepository(db, max_attempts=1)
    stage(db)
    store.admit(config, None)
    job = store.claim(config.config_hash, store.now())
    with psycopg.connect(db) as conn:
        conn.execute(
            "UPDATE embedding_jobs SET lease_expires_at=now()-interval '1 second' WHERE id=%s",
            (job.id,),
        )
    assert run(store, config).exit_code == 1
    assert run(store, config).exit_code == 0


def test_independent_heartbeat_keeps_slow_encoding_owned(db, config):
    store = KnowledgeRepository(db, lease_seconds=1)
    stage(db)
    store.admit(config, None)

    class Slow(Encoder):
        def encode_documents(self, texts):
            Event().wait(1.3)
            return super().encode_documents(texts)

    summary = run(store, config, Slow, heartbeat_seconds=0.1)
    assert summary.completed == 1 and summary.exit_code == 0


def test_job_created_before_but_available_after_cutoff_stays_pending(db, config):
    store = KnowledgeRepository(db)
    stage(db)
    store.admit(config, None)
    with psycopg.connect(db) as conn:
        conn.execute("UPDATE embedding_jobs SET available_at=now()+interval '1 hour'")
    summary = run(store, config)
    assert summary.completed == 0 and summary.deferred == 1 and summary.exit_code == 0
