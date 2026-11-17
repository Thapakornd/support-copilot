from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from support_copilot.infrastructure.postgres.knowledge_repository import (
    KnowledgeRepository,
)
from test_embedding_admission import stage


def test_documented_runtime_role_can_admit_without_model_identity_write(db, config):
    role = "embedding_runtime_" + uuid4().hex
    stage(db)
    with psycopg.connect(db, autocommit=True) as conn:
        conn.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD 'runtime_test_only'").format(
                sql.Identifier(role)
            )
        )
    try:
        with psycopg.connect(db) as conn:
            conn.execute(
                sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                    sql.Identifier(role)
                )
            )
            conn.execute(
                sql.SQL("GRANT SELECT ON categories,embedding_models TO {}").format(
                    sql.Identifier(role)
                )
            )
            conn.execute(
                sql.SQL("GRANT UPDATE(is_active) ON embedding_models TO {}").format(
                    sql.Identifier(role)
                )
            )
            conn.execute(
                sql.SQL("GRANT SELECT,UPDATE ON knowledge_documents TO {}").format(
                    sql.Identifier(role)
                )
            )
            conn.execute(
                sql.SQL(
                    "GRANT SELECT,INSERT ON knowledge_document_revisions,knowledge_revision_chunks,chunk_embeddings TO {}"
                ).format(sql.Identifier(role))
            )
            conn.execute(
                sql.SQL(
                    "GRANT SELECT,INSERT,UPDATE ON knowledge_chunk_sets,retrieval_publications,embedding_jobs TO {}"
                ).format(sql.Identifier(role))
            )
        runtime_dsn = make_conninfo(db, user=role, password="runtime_test_only")
        store = KnowledgeRepository(runtime_dsn)
        assert store.admit(config, ["doc-1"]).admitted == 1
        job = store.claim(config.config_hash, store.now())
        assert job.document_id == "doc-1"
        assert (
            store.publish(
                job,
                [
                    {
                        "chunk_id": "one",
                        "chunk_index": 0,
                        "heading_path": ["Help"],
                        "text": "Help body",
                        "char_count": 9,
                    }
                ],
                [[1, 0, 0]],
            )
            == "completed"
        )
        with (
            psycopg.connect(runtime_dsn) as conn,
            pytest.raises(psycopg.errors.InsufficientPrivilege),
        ):
            conn.execute(
                "UPDATE embedding_models SET dimensions=4 WHERE id=%s",
                (config.model_id,),
            )
    finally:
        with psycopg.connect(db, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
