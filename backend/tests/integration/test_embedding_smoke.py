"""Opt-in pinned, already-cached model smoke. Never downloads artifacts."""

import importlib.metadata
import json
import os
import platform
from threading import Event

import psycopg
import pytest
from psycopg import sql
from test_embedding_admission import stage

from support_copilot.core.config import WorkerSettings
from support_copilot.domain.embedding_job import validate_vectors
from support_copilot.infrastructure.embeddings.chunker import TokenAwareChunker
from support_copilot.infrastructure.embeddings.sentence_transformer import (
    SentenceTransformerEncoder,
)
from support_copilot.infrastructure.postgres.knowledge_repository import (
    KnowledgeRepository,
)
from support_copilot.interface.worker.main import run_once


@pytest.mark.skipif(
    os.getenv("EMBEDDING_MODEL_SMOKE") != "1",
    reason="Requires approved pinned model and explicitly provisioned offline cache",
)
def test_pinned_model_publication_lifecycle(db):
    settings = WorkerSettings(_env_file=None, database_url=db, offline=True)
    config = settings.effective_config()
    with psycopg.connect(db) as conn:
        conn.execute(
            sql.SQL(
                "ALTER TABLE chunk_embeddings ALTER COLUMN embedding TYPE vector({})"
            ).format(sql.Literal(config.dimensions))
        )
        conn.execute(
            "INSERT INTO embedding_models VALUES (%s,%s,%s,%s,%s,'cosine',true)",
            (
                config.model_id,
                config.provider,
                config.model_name,
                config.model_revision,
                config.dimensions,
            ),
        )
    store = KnowledgeRepository(db)
    instances = []

    def factory():
        instances.append(
            SentenceTransformerEncoder(config, device=settings.device, offline=True)
        )
        return instances[-1]

    def run():
        return run_once(store, factory, TokenAwareChunker(), config, Event())

    def pointer():
        with psycopg.connect(db) as conn:
            return conn.execute(
                "SELECT chunk_set_id FROM retrieval_publications WHERE document_id='doc-1'"
            ).fetchone()

    stage(db, "Initial help content.")
    assert store.admit(config, None).admitted == 1
    assert run().completed == 1
    assert len(instances) == 1
    first = pointer()
    validate_vectors(
        instances[0].encode_queries(["Where is help?"]), 1, config.dimensions
    )
    assert store.admit(config, None).unchanged == 1
    assert run().completed == 0 and len(instances) == 1
    stage(db, "Changed help content.")
    store.admit(config, None)
    assert run().completed == 1 and pointer() != first
    previous = pointer()
    stage(db, "Third revision must roll back.")
    store.admit(config, None)
    with psycopg.connect(db) as conn:
        conn.execute("""CREATE FUNCTION fail_smoke_publication() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'forced smoke failure'; END $$;
            CREATE TRIGGER fail_smoke_publication BEFORE UPDATE ON retrieval_publications
            FOR EACH ROW EXECUTE FUNCTION fail_smoke_publication()""")
    assert run().failed == 1 and pointer() == previous
    print(
        json.dumps(
            {
                "python": platform.python_version(),
                "os": platform.platform(),
                "torch": importlib.metadata.version("torch"),
                "sentence_transformers": importlib.metadata.version(
                    "sentence-transformers"
                ),
                "model_revision": config.model_revision,
                "device": settings.device,
            }
        )
    )
