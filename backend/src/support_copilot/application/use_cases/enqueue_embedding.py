"""Validate mutable staging data before admitting an immutable revision."""

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID

from support_copilot.application.ports import EmbeddingStorePort
from support_copilot.domain.embedding_job import (
    EmbeddingConfig,
    ProcessingError,
    canonical_json,
    sha256,
)


@dataclass(frozen=True)
class AdmissionResult:
    admitted: int = 0
    unchanged: int = 0
    rejected: int = 0


class AdmissionError(ProcessingError):
    def __init__(self, rejected=1):
        super().__init__("invalid_source")
        self.rejected = rejected


def canonical_snapshot(
    document_id: str, payload: dict, categories: dict[str, str]
) -> dict:
    if not isinstance(payload, dict) or payload.get("document_id") != document_id:
        raise AdmissionError()
    fields = (
        "title",
        "content_markdown",
        "source_url",
        "product",
        "deployment",
        "version_scope",
        "category",
        "source_type",
        "fetched_at",
    )
    if any(
        not isinstance(payload.get(key), str) or not payload[key].strip()
        for key in fields
    ):
        raise AdmissionError()
    snapshot = dict(payload)
    # Normalize transport line endings; retain whitespace carrying Markdown meaning.
    content = (
        payload["content_markdown"]
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .lstrip("\ufeff")
    )
    content_hash = sha256(content)
    if payload.get("content_hash") != content_hash:
        raise AdmissionError()
    aliases = {key.casefold(): key for key in categories}
    aliases.update({label.casefold(): key for key, label in categories.items()})
    # Compatibility with the existing curated source manifest.
    aliases.update({"authentication": "security", "performance": "performance"})
    category = aliases.get(payload["category"].strip().casefold())
    if category not in categories:
        raise AdmissionError()
    source_types = {
        "documentation": "documentation",
        "knowledge article": "knowledge_article",
        "knowledge_article": "knowledge_article",
        "resolved case": "resolved_case",
        "resolved_case": "resolved_case",
    }
    source_type = source_types.get(payload["source_type"].strip().casefold())
    topics = payload.get("topics")
    try:
        url = urlsplit(payload["source_url"])
        timestamp = datetime.fromisoformat(payload["fetched_at"])
        valid_url = (
            url.scheme in ("https", "http")
            and url.hostname
            and not url.username
            and not url.password
        )
    except ValueError:
        raise AdmissionError() from None
    if not valid_url or timestamp.tzinfo is None or not source_type:
        raise AdmissionError()
    if not isinstance(topics, list) or any(
        not isinstance(t, str) or not t.strip() for t in topics
    ):
        raise AdmissionError()
    snapshot.update(
        content_markdown=content,
        content_hash=content_hash,
        category=category,
        source_type=source_type,
        topics=sorted(set(topics)),
    )
    semantic = {
        key: snapshot[key]
        for key in (
            "content_markdown",
            "title",
            "source_url",
            "product",
            "deployment",
            "version_scope",
            "category",
            "topics",
            "source_type",
        )
    }
    snapshot["revision_hash"] = sha256(canonical_json(semantic))
    return snapshot


def enqueue(
    store: EmbeddingStorePort, config: EmbeddingConfig, document_ids: list[str] | None
) -> AdmissionResult:
    return store.admit(config, document_ids)


def retry_failed(store: EmbeddingStorePort, job_id: UUID) -> None:
    store.retry_failed(job_id)
