from dataclasses import replace

import psycopg
import pytest
from psycopg.types.json import Jsonb
from support_copilot.domain.embedding_job import ProcessingError
from support_copilot.infrastructure.postgres.knowledge_repository import (
    KnowledgeRepository,
)


def stage(db, text="First", document_id="doc-1", **changes):
    from support_copilot.domain.embedding_job import sha256

    body = "# Help\n\n" + text
    document = {
        "document_id": document_id,
        "title": "Help",
        "content_markdown": body,
        "content_hash": sha256(body),
        "source_url": "https://example.org/help",
        "fetch_url": "https://example.org/help.md",
        "source_type": "documentation",
        "product": "mongodb-atlas",
        "deployment": "atlas",
        "version_scope": "current",
        "category": "Connectivity",
        "topics": ["tls", "dns"],
        "fetched_at": "2026-11-16T00:00:00Z",
    }
    document.update(changes)
    with psycopg.connect(db) as conn:
        conn.execute(
            """INSERT INTO knowledge_documents(document_id,data) VALUES (%s,%s)
            ON CONFLICT(document_id) DO UPDATE SET data=EXCLUDED.data""",
            (document_id, Jsonb(document)),
        )


def test_admission_generation_reversion_and_configuration(db, config):
    store = KnowledgeRepository(db)
    stage(db)
    assert store.admit(config, None).admitted == 1
    stage(db, fetched_at="2026-11-17T00:00:00Z", topics=["dns", "tls"])
    assert store.admit(config, None).unchanged == 1
    stage(db, "Second")
    assert store.admit(config, None).admitted == 1
    stage(db)
    assert store.admit(config, None).admitted == 1
    with psycopg.connect(db) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM knowledge_document_revisions"
            ).fetchone()[0]
            == 2
        )
        assert (
            conn.execute(
                "SELECT ingestion_generation FROM knowledge_documents"
            ).fetchone()[0]
            == 3
        )
    assert (
        store.admit(replace(config, document_prompt="document: "), None).admitted == 1
    )


def test_invalid_batch_and_unknown_selection_roll_back(db, config):
    store = KnowledgeRepository(db)
    stage(db)
    stage(db, document_id="bad", category="unknown")
    with pytest.raises(ProcessingError):
        store.admit(config, None)
    with psycopg.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM embedding_jobs").fetchone()[0] == 0
        assert (
            conn.execute(
                "SELECT count(*) FROM knowledge_document_revisions"
            ).fetchone()[0]
            == 0
        )
    with pytest.raises(ProcessingError):
        store.admit(config, ["missing"])


def test_retry_only_current_failed_target(db, config):
    store = KnowledgeRepository(db)
    stage(db)
    store.admit(config, None)
    job = store.claim(config.config_hash, store.now())
    with pytest.raises(ProcessingError):
        store.retry_failed(job.id)
    assert store.fail(job, "invalid_source", False) == "failed"
    assert store.admit(config, None).unchanged == 1
    store.retry_failed(job.id)
    again = store.claim(config.config_hash, store.now())
    assert again.attempts == 1
    store.fail(again, "invalid_source", False)
    stage(db, "New target")
    store.admit(config, None)
    with pytest.raises(ProcessingError):
        store.retry_failed(job.id)
