"""Bounded document preparation and inference; the store owns atomic publication."""

import json
import logging
from collections.abc import Callable

from support_copilot.application.ports import (
    ChunkerPort,
    EmbeddingStorePort,
    EncoderPort,
)
from support_copilot.domain.embedding_job import (
    EmbeddingJob,
    ProcessingError,
    validate_vectors,
)

logger = logging.getLogger(__name__)


def process_job(
    store: EmbeddingStorePort,
    job: EmbeddingJob,
    chunker: ChunkerPort,
    encoder: EncoderPort,
    stopped: Callable[[], bool],
    *,
    batch_size: int = 32,
) -> str:
    if batch_size <= 0:
        raise ValueError("Batch size must be positive")
    if not store.is_current(job):
        return "superseded"
    chunks = chunker.chunks(store.load_snapshot(job), job.config, encoder)
    logger.info(
        json.dumps(
            {
                "event": "prepared",
                "job_id": str(job.id),
                "document_id": job.document_id,
                "revision_id": str(job.revision_id),
                "generation": job.generation,
                "config_hash": job.config.config_hash,
                "attempt": job.attempts,
                "chunk_count": len(chunks),
            }
        )
    )
    vectors = []
    for start in range(0, len(chunks), batch_size):
        if stopped():
            raise ProcessingError("interrupted", retryable=True)
        batch = chunks[start : start + batch_size]
        encoded = encoder.encode_documents([chunk["text"] for chunk in batch])
        validate_vectors(encoded, len(batch), job.config.dimensions)
        vectors.extend(encoded)
    validate_vectors(vectors, len(chunks), job.config.dimensions)
    if stopped():
        raise ProcessingError("interrupted", retryable=True)
    return store.publish(job, chunks, vectors)
