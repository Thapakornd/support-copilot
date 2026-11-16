"""Durable claims and ownership fencing. Operations needing both lock document first."""

from datetime import datetime
from uuid import uuid4

from support_copilot.domain.embedding_job import (
    EmbeddingConfig,
    EmbeddingJob,
    OwnershipLost,
    ProcessingError,
    QueueObservation,
    RecoveryResult,
)
from support_copilot.infrastructure.postgres.connection import Database


def current(document, job) -> bool:
    return bool(
        document["is_active"]
        and document["requested_revision_id"] == job["revision_id"]
        and document["ingestion_generation"] == job["generation"]
        and document["requested_embedding_config_hash"] == job["config_hash"]
    )


def lock_owned(conn, job):
    document = conn.execute(
        "SELECT * FROM knowledge_documents WHERE document_id=%s FOR UPDATE",
        (job.document_id,),
    ).fetchone()
    row = conn.execute(
        "SELECT *,lease_expires_at>clock_timestamp() AS live FROM embedding_jobs WHERE id=%s FOR UPDATE",
        (job.id,),
    ).fetchone()
    if (
        not row
        or row["status"] != "processing"
        or row["claim_token"] != job.claim_token
        or not row["live"]
    ):
        raise OwnershipLost()
    return document, row


def finish(conn, job_id, status):
    conn.execute(
        """UPDATE embedding_jobs SET status=%s,claim_token=NULL,lease_expires_at=NULL,
        updated_at=clock_timestamp(),finished_at=clock_timestamp() WHERE id=%s""",
        (status, job_id),
    )


def finish_owned(conn, job, status):
    updated = conn.execute(
        """UPDATE embedding_jobs SET status=%s,claim_token=NULL,lease_expires_at=NULL,
        updated_at=clock_timestamp(),finished_at=clock_timestamp()
        WHERE id=%s AND status='processing' AND claim_token=%s AND lease_expires_at>clock_timestamp()
        RETURNING id""",
        (status, job.id, job.claim_token),
    ).fetchone()
    if not updated:
        raise OwnershipLost()


class PostgresEmbeddingStore:
    def __init__(self, dsn: str, *, lease_seconds: int = 300, max_attempts: int = 3):
        self.db = Database(dsn)
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts
        if lease_seconds <= 0 or max_attempts <= 0:
            raise ValueError("Lease and attempt limits must be positive")

    def now(self) -> datetime:
        with self.db.transaction() as conn:
            return conn.execute("SELECT clock_timestamp() AS t").fetchone()["t"]

    def claim(self, config_hash: str, cutoff: datetime) -> EmbeddingJob | None:
        with self.db.transaction() as conn:
            row = conn.execute(
                """SELECT * FROM embedding_jobs WHERE status='pending'
                AND config_hash=%s AND created_at<=%s AND available_at<=%s AND attempts<max_attempts
                ORDER BY available_at,created_at,id FOR UPDATE SKIP LOCKED LIMIT 1""",
                (config_hash, cutoff, cutoff),
            ).fetchone()
            if row is None:
                return None
            token = uuid4()
            conn.execute(
                """UPDATE embedding_jobs SET status='processing',attempts=attempts+1,
                claim_token=%s,lease_expires_at=clock_timestamp()+(%s * interval '1 second'),
                updated_at=clock_timestamp() WHERE id=%s""",
                (token, self.lease_seconds, row["id"]),
            )
            return EmbeddingJob(
                row["id"],
                row["document_id"],
                row["revision_id"],
                row["generation"],
                EmbeddingConfig.from_dict(row["config"]),
                row["attempts"] + 1,
                token,
            )

    def renew(self, job: EmbeddingJob) -> bool:
        with self.db.transaction() as conn:
            return (
                conn.execute(
                    """UPDATE embedding_jobs SET
                lease_expires_at=clock_timestamp()+(%s * interval '1 second'), updated_at=clock_timestamp()
                WHERE id=%s AND status='processing' AND claim_token=%s AND lease_expires_at>clock_timestamp()
                RETURNING id""",
                    (self.lease_seconds, job.id, job.claim_token),
                ).fetchone()
                is not None
            )

    def recover(self, cutoff: datetime) -> RecoveryResult:
        result = RecoveryResult()
        with self.db.transaction() as conn:
            candidates = conn.execute(
                """SELECT id,document_id FROM embedding_jobs WHERE created_at<=%s
                AND (status='pending' OR (status='processing' AND lease_expires_at<=%s))
                ORDER BY document_id,id""",
                (cutoff, cutoff),
            ).fetchall()
            for candidate in candidates:
                document = conn.execute(
                    "SELECT * FROM knowledge_documents WHERE document_id=%s FOR UPDATE SKIP LOCKED",
                    (candidate["document_id"],),
                ).fetchone()
                if not document:
                    continue
                row = conn.execute(
                    "SELECT * FROM embedding_jobs WHERE id=%s FOR UPDATE SKIP LOCKED",
                    (candidate["id"],),
                ).fetchone()
                if not row or row["status"] not in ("pending", "processing"):
                    continue
                if row["status"] == "processing" and row["lease_expires_at"] > cutoff:
                    continue
                if not current(document, row):
                    finish(conn, row["id"], "superseded")
                    result.superseded += 1
                elif row["status"] == "processing":
                    if row["attempts"] >= row["max_attempts"]:
                        finish(conn, row["id"], "failed")
                        conn.execute(
                            "UPDATE embedding_jobs SET last_error_code='lease_exhausted',last_error='lease_exhausted' WHERE id=%s",
                            (row["id"],),
                        )
                        result.failed += 1
                    else:
                        conn.execute(
                            """UPDATE embedding_jobs SET status='pending',claim_token=NULL,
                            lease_expires_at=NULL,available_at=%s,updated_at=clock_timestamp() WHERE id=%s""",
                            (cutoff, row["id"]),
                        )
                        result.recovered += 1
        return result

    def is_current(self, job: EmbeddingJob) -> bool:
        with self.db.transaction() as conn:
            document, row = lock_owned(conn, job)
            if not current(document, row):
                finish_owned(conn, job, "superseded")
                return False
            return True

    def fail(self, job: EmbeddingJob, code: str, retryable: bool) -> str:
        # Diagnostics are code-only: never persist arbitrary exception strings.
        safe_code = code if code in SAFE_CODES else "processing_error"
        with self.db.transaction() as conn:
            document, row = lock_owned(conn, job)
            if not current(document, row):
                finish_owned(conn, job, "superseded")
                return "superseded"
            status = (
                "pending"
                if retryable and row["attempts"] < row["max_attempts"]
                else "failed"
            )
            delay = min(60 * 2 ** min(row["attempts"] - 1, 6), 3600)
            updated = conn.execute(
                """UPDATE embedding_jobs SET status=%s,claim_token=NULL,lease_expires_at=NULL,
                last_error_code=%s,last_error=%s,updated_at=clock_timestamp(),
                available_at=clock_timestamp()+(%s * interval '1 second'),
                finished_at=CASE WHEN %s='failed' THEN clock_timestamp() ELSE NULL END
                WHERE id=%s AND status='processing' AND claim_token=%s AND lease_expires_at>clock_timestamp()
                RETURNING id""",
                (status, safe_code, safe_code, delay, status, job.id, job.claim_token),
            ).fetchone()
            if not updated:
                raise OwnershipLost()
            return status

    def observe(self, config_hash: str, cutoff: datetime) -> QueueObservation:
        with self.db.transaction() as conn:
            rows = conn.execute(
                """SELECT j.*,d.is_active,d.requested_revision_id,d.ingestion_generation,
                d.requested_embedding_config_hash FROM embedding_jobs j JOIN knowledge_documents d USING(document_id)
                WHERE j.status IN ('pending','processing') AND j.created_at<=%s""",
                (cutoff,),
            ).fetchall()
            result = QueueObservation()
            for row in rows:
                if not current(row, row):
                    continue
                if row["status"] == "processing":
                    result.owned_elsewhere += 1
                elif row["available_at"] > cutoff:
                    result.deferred += 1
                elif row["config_hash"] != config_hash:
                    result.blocked += 1
            return result

    def validate_configuration(self, config):
        with self.db.transaction() as conn:
            validate_configuration(conn, config)


def validate_configuration(conn, config):
    model = conn.execute(
        "SELECT * FROM embedding_models WHERE id=%s FOR SHARE", (config.model_id,)
    ).fetchone()
    if (
        not model
        or not model["is_active"]
        or any(
            (
                model["provider"] != config.provider,
                model["model_name"] != config.model_name,
                model["model_revision"] != config.model_revision,
                model["dimensions"] != config.dimensions,
                model["distance_metric"] != "cosine",
            )
        )
    ):
        raise ProcessingError("model_registry_mismatch")
    column = conn.execute("""SELECT format_type(atttypid,atttypmod) AS type FROM pg_attribute
        WHERE attrelid='public.chunk_embeddings'::regclass AND attname='embedding' AND NOT attisdropped""").fetchone()
    if not column or column["type"] != f"vector({config.dimensions})":
        raise ProcessingError("schema_dimension_mismatch")


SAFE_CODES = frozenset(
    {
        "encoding_resource",
        "database_unavailable",
        "model_registry_mismatch",
        "schema_dimension_mismatch",
        "model_unavailable",
        "model_dimension_mismatch",
        "tokenizer_limit_mismatch",
        "vector_coverage",
        "vector_dimensions_or_finiteness",
        "vector_not_normalized",
        "invalid_source",
        "empty_document",
        "oversized_block",
        "heading_overhead",
        "document_budget",
        "interrupted",
        "encoding_failed",
        "processing_error",
        "configuration_mismatch",
    }
)
