"""Knowledge transactions, using the same connection for every related write."""

import json
import logging
from uuid import uuid4

from psycopg.types.json import Jsonb
from support_copilot.application.use_cases.enqueue_embedding import (
    AdmissionError,
    AdmissionResult,
    canonical_snapshot,
)
from support_copilot.domain.embedding_job import ProcessingError
from support_copilot.infrastructure.postgres.embedding_jobs import (
    SAFE_CODES,
    PostgresEmbeddingStore,
    current,
    validate_configuration,
)

logger = logging.getLogger(__name__)


class KnowledgeRepository(PostgresEmbeddingStore):
    def load_snapshot(self, job):
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT source_payload FROM knowledge_document_revisions WHERE id=%s AND document_id=%s",
                (job.revision_id, job.document_id),
            ).fetchone()
            if not row:
                raise ProcessingError("invalid_source")
            return row["source_payload"]

    def publish(self, job, chunks, vectors):
        from support_copilot.domain.embedding_job import OwnershipLost, validate_vectors
        from support_copilot.infrastructure.postgres.embedding_jobs import (
            finish,
            lock_owned,
        )

        validate_vectors(vectors, len(chunks), job.config.dimensions)
        if (
            [chunk["chunk_index"] for chunk in chunks] != list(range(len(chunks)))
            or len({chunk["chunk_id"] for chunk in chunks}) != len(chunks)
            or any(
                not chunk["text"].strip() or chunk["char_count"] != len(chunk["text"])
                for chunk in chunks
            )
        ):
            raise ProcessingError("vector_coverage")
        with self.db.transaction() as conn:
            document, row = lock_owned(conn, job)
            if not current(document, row):
                finish(conn, job.id, "superseded")
                return "superseded"
            if row["config_hash"] != job.config.config_hash:
                raise ProcessingError("configuration_mismatch")
            validate_configuration(conn, job.config)
            chunk_set_id = uuid4()
            conn.execute(
                """INSERT INTO knowledge_chunk_sets(id,revision_id,chunker_version,config_hash,state)
                VALUES (%s,%s,%s,%s,'preparing') ON CONFLICT(revision_id,chunker_version,config_hash) DO NOTHING""",
                (
                    chunk_set_id,
                    job.revision_id,
                    job.config.chunker_version,
                    job.config.config_hash,
                ),
            )
            chunk_set_id = conn.execute(
                "SELECT id FROM knowledge_chunk_sets WHERE revision_id=%s AND chunker_version=%s AND config_hash=%s FOR UPDATE",
                (job.revision_id, job.config.chunker_version, job.config.config_hash),
            ).fetchone()["id"]
            for chunk, vector in zip(chunks, vectors, strict=True):
                conn.execute(
                    """INSERT INTO knowledge_chunks(chunk_set_id,chunk_id,chunk_index,heading_path,text,char_count,oversized)
                    VALUES (%s,%s,%s,%s,%s,%s,false) ON CONFLICT(chunk_set_id,chunk_id) DO NOTHING""",
                    (
                        chunk_set_id,
                        chunk["chunk_id"],
                        chunk["chunk_index"],
                        chunk["heading_path"],
                        chunk["text"],
                        len(chunk["text"]),
                    ),
                )
                conn.execute(
                    """INSERT INTO chunk_embeddings(chunk_set_id,chunk_id,model_id,embedding)
                    VALUES (%s,%s,%s,%s::vector) ON CONFLICT(chunk_set_id,chunk_id,model_id) DO NOTHING""",
                    (
                        chunk_set_id,
                        chunk["chunk_id"],
                        job.config.model_id,
                        "[" + ",".join(str(float(v)) for v in vector) + "]",
                    ),
                )
            stored = conn.execute(
                """SELECT c.chunk_id,c.chunk_index,c.text,c.heading_path,e.embedding::text AS embedding
                FROM knowledge_chunks c LEFT JOIN chunk_embeddings e ON e.chunk_set_id=c.chunk_set_id
                AND e.chunk_id=c.chunk_id AND e.model_id=%s WHERE c.chunk_set_id=%s ORDER BY c.chunk_index""",
                (job.config.model_id, chunk_set_id),
            ).fetchall()
            if len(stored) != len(chunks) or any(
                existing["chunk_id"] != expected["chunk_id"]
                or existing["text"] != expected["text"]
                or existing["heading_path"] != expected["heading_path"]
                or existing["embedding"] is None
                for existing, expected in zip(stored, chunks, strict=True)
            ):
                raise ProcessingError("vector_coverage")
            validate_vectors(
                [json.loads(item["embedding"]) for item in stored],
                len(chunks),
                job.config.dimensions,
            )
            conn.execute(
                "UPDATE knowledge_chunk_sets SET state='ready' WHERE id=%s",
                (chunk_set_id,),
            )
            conn.execute(
                """INSERT INTO retrieval_publications(document_id,chunk_set_id,model_id,published_at)
                VALUES (%s,%s,%s,clock_timestamp()) ON CONFLICT(document_id) DO UPDATE SET
                chunk_set_id=EXCLUDED.chunk_set_id,model_id=EXCLUDED.model_id,published_at=EXCLUDED.published_at""",
                (job.document_id, chunk_set_id, job.config.model_id),
            )
            conn.execute(
                "UPDATE knowledge_documents SET current_revision_id=%s,updated_at=clock_timestamp() WHERE document_id=%s",
                (job.revision_id, job.document_id),
            )
            # Late fencing rolls back all artifacts if the lease expired during writes.
            owned = conn.execute(
                """UPDATE embedding_jobs SET status='completed',claim_token=NULL,
                lease_expires_at=NULL,updated_at=clock_timestamp(),finished_at=clock_timestamp()
                WHERE id=%s AND status='processing' AND claim_token=%s AND lease_expires_at>clock_timestamp()
                RETURNING id""",
                (job.id, job.claim_token),
            ).fetchone()
            if not owned:
                raise OwnershipLost()
            return "completed"

    def admit(self, config, document_ids=None):
        with self.db.transaction() as conn:
            validate_configuration(conn, config)
            categories = {
                r["id"]: r["label"]
                for r in conn.execute("SELECT id,label FROM categories")
            }
            if document_ids is None:
                documents = conn.execute(
                    "SELECT * FROM knowledge_documents ORDER BY document_id FOR UPDATE"
                ).fetchall()
            else:
                selected = sorted(set(document_ids))
                documents = conn.execute(
                    "SELECT * FROM knowledge_documents WHERE document_id=ANY(%s) ORDER BY document_id FOR UPDATE",
                    (selected,),
                ).fetchall()
                if len(documents) != len(selected) or not selected:
                    raise AdmissionError(max(1, len(selected) - len(documents)))
            snapshots = []
            rejected = 0
            for document in documents:
                try:
                    if not document["is_active"]:
                        raise AdmissionError()
                    snapshots.append(
                        canonical_snapshot(
                            document["document_id"], document["data"], categories
                        )
                    )
                except AdmissionError:
                    rejected += 1
            if rejected:
                raise AdmissionError(rejected)
            admitted = unchanged = 0
            for document, snapshot in zip(documents, snapshots, strict=True):
                revision = conn.execute(
                    """INSERT INTO knowledge_document_revisions
                    (id,document_id,revision_hash,content_hash,title,source_url,source_type,product,deployment,
                    version_scope,category_id,topics,content_markdown,excerpt,source_payload,fetched_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(document_id,revision_hash) DO NOTHING RETURNING id""",
                    (
                        uuid4(),
                        document["document_id"],
                        snapshot["revision_hash"],
                        snapshot["content_hash"],
                        snapshot["title"],
                        snapshot["source_url"],
                        snapshot["source_type"],
                        snapshot["product"],
                        snapshot["deployment"],
                        snapshot["version_scope"],
                        snapshot["category"],
                        snapshot["topics"],
                        snapshot["content_markdown"],
                        snapshot["content_markdown"][:500],
                        Jsonb(snapshot),
                        snapshot["fetched_at"],
                    ),
                ).fetchone()
                if revision is None:
                    revision = conn.execute(
                        "SELECT id FROM knowledge_document_revisions WHERE document_id=%s AND revision_hash=%s",
                        (document["document_id"], snapshot["revision_hash"]),
                    ).fetchone()
                revision_id = revision["id"]
                if (
                    document["requested_revision_id"] == revision_id
                    and document["requested_embedding_config_hash"]
                    == config.config_hash
                ):
                    unchanged += 1
                    continue
                generation = document["ingestion_generation"] + 1
                conn.execute(
                    """UPDATE knowledge_documents SET requested_revision_id=%s,ingestion_generation=%s,
                    requested_embedding_config_hash=%s,updated_at=clock_timestamp() WHERE document_id=%s""",
                    (
                        revision_id,
                        generation,
                        config.config_hash,
                        document["document_id"],
                    ),
                )
                conn.execute(
                    """INSERT INTO embedding_jobs
                    (id,document_id,revision_id,generation,model_id,chunker_version,config_hash,config,max_attempts)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        uuid4(),
                        document["document_id"],
                        revision_id,
                        generation,
                        config.model_id,
                        config.chunker_version,
                        config.config_hash,
                        Jsonb(json.loads(config.canonical_json())),
                        self.max_attempts,
                    ),
                )
                admitted += 1
            return AdmissionResult(admitted, unchanged)

    def retry_failed(self, job_id):
        with self.db.transaction() as conn:
            candidate = conn.execute(
                "SELECT document_id FROM embedding_jobs WHERE id=%s", (job_id,)
            ).fetchone()
            if not candidate:
                raise ProcessingError("retry_not_current_failed")
            document = conn.execute(
                "SELECT * FROM knowledge_documents WHERE document_id=%s FOR UPDATE",
                (candidate["document_id"],),
            ).fetchone()
            row = conn.execute(
                "SELECT * FROM embedding_jobs WHERE id=%s FOR UPDATE", (job_id,)
            ).fetchone()
            if row["status"] != "failed" or not current(document, row):
                raise ProcessingError("retry_not_current_failed")
            # Only trusted codes; do not log historical arbitrary diagnostic text.
            logger.info(
                "retry_job id=%s previous_error=%s",
                job_id,
                row["last_error_code"]
                if row["last_error_code"] in SAFE_CODES
                else "processing_error",
            )
            conn.execute(
                """UPDATE embedding_jobs SET status='pending',attempts=0,
                available_at=clock_timestamp(),updated_at=clock_timestamp(),finished_at=NULL,
                last_error_code=NULL,last_error=NULL WHERE id=%s""",
                (job_id,),
            )
