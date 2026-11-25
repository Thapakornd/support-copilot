from copy import deepcopy

import pytest

from support_copilot.application.use_cases.enqueue_embedding import canonical_snapshot
from support_copilot.domain.embedding_job import ProcessingError, sha256


def payload(body="# Help\n\nBody Ω."):
    return {
        "document_id": "doc-1",
        "title": "Help",
        "content_markdown": body,
        "content_hash": sha256(body),
        "source_url": "https://example.org/help",
        "fetch_url": "https://example.org/help.md",
        "product": "mongodb-atlas",
        "deployment": "atlas",
        "version_scope": "current",
        "category": "Connectivity",
        "topics": ["tls", "dns"],
        "source_type": "documentation",
        "fetched_at": "2026-11-16T00:00:00Z",
    }


def test_semantic_hash_ignores_fetch_and_sorts_topics():
    a = payload()
    b = deepcopy(a)
    b.update(
        fetched_at="2026-11-17T00:00:00Z",
        topics=["dns", "tls"],
        fetch_url="https://example.org/new",
    )
    first = canonical_snapshot("doc-1", a, {"connectivity": "Connectivity"})
    second = canonical_snapshot("doc-1", b, {"connectivity": "Connectivity"})
    assert first["revision_hash"] == second["revision_hash"]
    assert first["category"] == "connectivity"
    b["title"] = "Changed title"
    assert (
        canonical_snapshot("doc-1", b, {"connectivity": "Connectivity"})[
            "revision_hash"
        ]
        != first["revision_hash"]
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("content_hash", "forged"),
        ("category", "Unknown"),
        ("topics", "dns"),
        ("source_url", "javascript:bad"),
        ("fetched_at", "yesterday"),
        ("title", " "),
        ("document_id", "other"),
        ("source_type", "arbitrary"),
    ],
)
def test_invalid_promotion_is_rejected(field, value):
    document = payload()
    document[field] = value
    with pytest.raises(ProcessingError):
        canonical_snapshot("doc-1", document, {"connectivity": "Connectivity"})


def test_existing_manifest_category_aliases():
    document = payload()
    document["category"] = "Authentication"
    assert (
        canonical_snapshot("doc-1", document, {"security": "Security & access"})[
            "category"
        ]
        == "security"
    )
    document["category"] = "Performance"
    assert (
        canonical_snapshot("doc-1", document, {"performance": "Performance & memory"})[
            "category"
        ]
        == "performance"
    )
