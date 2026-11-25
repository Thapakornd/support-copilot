from support_copilot.domain.embedding_job import EmbeddingConfig, validate_vectors
from support_copilot.domain.entities import RetrievedPassage
from support_copilot.infrastructure.postgres.connection import Database
from support_copilot.infrastructure.postgres.embedding_jobs import (
    validate_configuration,
)


class PostgresRetriever:
    def __init__(self, dsn: str, config: EmbeddingConfig):
        self.db = Database(dsn)
        self.config = config
        self.config_hash = config.config_hash

    def validate_configuration(self) -> None:
        with self.db.transaction(read_only=True) as conn:
            validate_configuration(conn, self.config, lock_model=False)

    def resolve_category(self, category: str) -> str | None:
        with self.db.transaction(read_only=True) as conn:
            rows = conn.execute(
                """SELECT id FROM categories WHERE id=%(category)s OR label=%(category)s
                   ORDER BY (id=%(category)s) DESC, id LIMIT 2""",
                {"category": category},
            ).fetchall()
        if len(rows) == 1 or (rows and rows[0]["id"] == category):
            return rows[0]["id"]
        return None

    def retrieve(
        self, vector: list[float], category: str | None, limit: int
    ) -> list[RetrievedPassage]:
        validate_vectors([vector], 1, self.config.dimensions)
        if limit < 1:
            raise ValueError("Candidate limit must be positive")

        # Sorting by the distance expression plus zero keeps cosine search exact
        # even if an approximate vector index exists on the embeddings table.
        with self.db.transaction(read_only=True) as conn:
            rows = conn.execute(
                """SELECT p.document_id, r.id::text AS revision_id, s.id::text AS chunk_set_id,
                          c.chunk_id, r.title, r.source_url, c.heading_path, c.text,
                          (e.embedding <=> %(vector)s::vector) + 0 AS distance
                   FROM retrieval_publications p
                   JOIN knowledge_documents d ON d.document_id = p.document_id AND d.is_active
                   JOIN knowledge_chunk_sets s ON s.id = p.chunk_set_id AND s.state = 'ready'
                   JOIN knowledge_document_revisions r ON r.id = s.revision_id
                       AND r.document_id = d.document_id AND r.id = d.current_revision_id
                   JOIN embedding_models m ON m.id = p.model_id AND m.is_active
                   JOIN chunk_embeddings e ON e.chunk_set_id = s.id AND e.model_id = m.id
                   JOIN knowledge_revision_chunks c ON c.chunk_set_id = e.chunk_set_id
                       AND c.chunk_id = e.chunk_id
                   WHERE p.model_id = %(model_id)s AND s.config_hash = %(config_hash)s
                       AND (%(category)s::text IS NULL OR r.category_id = %(category)s::text)
                   ORDER BY distance, p.document_id, c.chunk_index
                   LIMIT %(limit)s""",
                {
                    "vector": "["
                    + ",".join(str(float(value)) for value in vector)
                    + "]",
                    "model_id": self.config.model_id,
                    "config_hash": self.config_hash,
                    "category": category,
                    "limit": limit,
                },
            ).fetchall()
        return [
            RetrievedPassage(**{**row, "heading_path": tuple(row["heading_path"])})
            for row in rows
        ]
