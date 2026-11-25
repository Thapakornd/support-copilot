from dataclasses import replace
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from test_embedding_admission import stage
from test_embedding_publication import chunks

from support_copilot.domain.embedding_job import ProcessingError
from support_copilot.infrastructure.postgres.knowledge_repository import (
    KnowledgeRepository,
)


def make_retriever(db, config):
    from support_copilot.infrastructure.postgres import retrieval

    return retrieval.PostgresRetriever(db, config)


def publish(db, store, config, document_id, text, vector, **metadata):
    stage(db, text, document_id=document_id, **metadata)
    store.admit(config, [document_id])
    job = store.claim(config.config_hash, store.now())
    assert store.publish(job, chunks(text), [vector]) == "completed"
    return job


def test_retrieval_uses_previous_revision_until_replacement_commits(db, config):
    store = KnowledgeRepository(db)
    first = publish(db, store, config, "doc-1", "Old passage", [1, 0, 0])
    stage(db, "New passage", title="Updated Help")
    store.admit(config, ["doc-1"])
    replacement = store.claim(config.config_hash, store.now())
    retriever = make_retriever(db, config)

    [old] = retriever.retrieve([1, 0, 0], None, 10)
    assert (old.revision_id, old.text, old.title) == (
        str(first.revision_id),
        "Old passage",
        "Help",
    )
    assert store.publish(replacement, chunks("New passage"), [[1, 0, 0]]) == "completed"
    [new] = retriever.retrieve([1, 0, 0], "connectivity", 10)
    assert (new.document_id, new.revision_id, new.text, new.title) == (
        "doc-1",
        str(replacement.revision_id),
        "New passage",
        "Updated Help",
    )
    assert new.chunk_set_id != old.chunk_set_id
    assert (new.chunk_id, new.heading_path, new.source_url, new.distance) == (
        "chunk_1",
        ("Help",),
        "https://example.org/help",
        0.0,
    )


def test_retrieval_filters_by_publication_model_config_activity_and_category(
    db, config
):
    store = KnowledgeRepository(db)
    publish(db, store, config, "match", "Match", [1, 0, 0])
    publish(db, store, config, "farther", "Farther", [0, 1, 0])
    publish(db, store, config, "inactive", "Inactive", [1, 0, 0])
    publish(
        db,
        store,
        config,
        "other-category",
        "Security",
        [1, 0, 0],
        category="Security & access",
    )
    publish(
        db,
        store,
        replace(config, query_prompt="incompatible: "),
        "old-config",
        "Wrong prompt",
        [1, 0, 0],
    )
    other = replace(config, model_id=uuid4(), model_name="other/model")
    with psycopg.connect(db) as conn:
        conn.execute(
            "UPDATE knowledge_documents SET is_active=false WHERE document_id='inactive'"
        )
        conn.execute(
            "INSERT INTO embedding_models VALUES (%s,'sentence-transformers',%s,%s,3,'cosine',true)",
            (other.model_id, other.model_name, other.model_revision),
        )
    publish(db, store, other, "other-model", "Wrong model", [1, 0, 0])
    retriever = make_retriever(db, config)

    assert [
        p.document_id for p in retriever.retrieve([1, 0, 0], "connectivity", 10)
    ] == ["match", "farther"]
    assert [
        p.document_id for p in retriever.retrieve([1, 0, 0], "connectivity", 1)
    ] == ["match"]
    assert {p.document_id for p in retriever.retrieve([1, 0, 0], None, 10)} == {
        "match",
        "farther",
        "other-category",
    }


def test_retriever_resolves_category_ids_and_labels(db, config):
    retriever = make_retriever(db, config)
    assert retriever.resolve_category("connectivity") == "connectivity"
    assert retriever.resolve_category("Security & access") == "security"
    assert retriever.resolve_category("unknown") is None


def test_startup_checks_model_and_schema_using_a_read_only_connection(db, config):
    with psycopg.connect(db, autocommit=True) as conn:
        conn.execute(
            sql.SQL("ALTER DATABASE {} SET default_transaction_read_only=on").format(
                sql.Identifier(conn.info.dbname)
            )
        )
    retriever = make_retriever(db, config)
    retriever.validate_configuration()
    with pytest.raises(ProcessingError, match="model_registry_mismatch"):
        make_retriever(
            db, replace(config, model_revision="b" * 40)
        ).validate_configuration()
