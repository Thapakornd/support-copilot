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
