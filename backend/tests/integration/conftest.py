"""Opt-in tests: each case creates its own database, never drops a supplied DB."""

import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo


@pytest.fixture(params=[False, True], ids=["empty-schema", "legacy-staging"])
def db(request):
    dsn = os.getenv("EMBEDDING_TEST_DSN")
    if not dsn:
        pytest.skip("Set EMBEDDING_TEST_DSN to a disposable PostgreSQL cluster")
    name = "embedding_test_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    test_dsn = make_conninfo(dsn, dbname=name)
    root = Path(__file__).resolve().parents[2] / "sql"
    try:
        with psycopg.connect(test_dsn, autocommit=True) as conn:
            if request.param:
                conn.execute(
                    "CREATE TABLE knowledge_documents(document_id text PRIMARY KEY,data jsonb NOT NULL)"
                )
                conn.execute(
                    "INSERT INTO knowledge_documents VALUES ('legacy-staging','{\"kept\":true}')"
                )
            conn.execute((root / "001_schema.sql").read_text())
            conn.execute((root / "003_seed_reference.sql").read_text())
            conn.execute("CREATE EXTENSION vector")
            # 002 is a psql script. This is its SQL at the test model's dimension.
            conn.execute("""CREATE TABLE chunk_embeddings (
                chunk_set_id uuid NOT NULL, chunk_id text NOT NULL,
                model_id uuid NOT NULL REFERENCES embedding_models,
                embedding vector(3) NOT NULL, created_at timestamptz DEFAULT now(),
                PRIMARY KEY(chunk_set_id, chunk_id, model_id),
                FOREIGN KEY(chunk_set_id, chunk_id) REFERENCES knowledge_chunks)""")
            conn.execute((root / "004_embedding_jobs.sql").read_text())
            if request.param:
                assert conn.execute(
                    "SELECT data FROM knowledge_documents WHERE document_id='legacy-staging'"
                ).fetchone()[0] == {"kept": True}
                conn.execute(
                    "DELETE FROM knowledge_documents WHERE document_id='legacy-staging'"
                )
        yield test_dsn
    finally:
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )
