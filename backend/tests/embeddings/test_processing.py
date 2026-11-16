from dataclasses import replace
from uuid import uuid4

import pytest
from support_copilot.domain.embedding_job import (
    EmbeddingConfig,
    ProcessingError,
    sha256,
    validate_vectors,
)
from support_copilot.infrastructure.embeddings.chunker import TokenAwareChunker


class CharacterEncoder:
    def token_count(self, text, *, query=False):
        return len(text) + 10  # prompt and special-token overhead

    def encode_documents(self, texts):
        return [[1.0, 0.0, 0.0] for text in texts]


def config(**changes):
    return replace(
        EmbeddingConfig(uuid4(), "approved/test", "a" * 40, 3, 100, "p: ", "q: "),
        **changes,
    )


def snapshot(body):
    return {
        "document_id": "doc-1",
        "content_markdown": body,
        "content_hash": sha256(body),
        "title": "Help",
        "source_url": "https://example.org",
        "fetch_url": "https://example.org.md",
        "product": "Atlas",
        "deployment": "atlas",
        "version_scope": "current",
        "category": "connectivity",
        "topics": ["dns"],
        "source_type": "documentation",
    }


def test_token_splitting_preserves_unicode_unbroken_body_and_headings():
    same_config = config()
    body = "Ω" * 501
    chunks = TokenAwareChunker().chunks(
        snapshot("# Help\n\n" + body), same_config, CharacterEncoder()
    )
    assert len(chunks) > 1
    assert all(len(chunk["text"]) + 10 <= 100 for chunk in chunks)
    assert "".join(chunk["text"].removeprefix("# Help\n\n") for chunk in chunks) == body
    assert all(chunk["heading_path"] == ["Help"] for chunk in chunks)
    assert chunks == TokenAwareChunker().chunks(
        snapshot("# Help\n\n" + body), same_config, CharacterEncoder()
    )


@pytest.mark.parametrize(
    "body,code",
    [
        ("# Help\n\n```sh\n" + "x" * 200 + "\n```", "oversized_block"),
        ("# Help\n\n| a | b |\n|---|---|\n|" + "x" * 200 + "|", "oversized_block"),
        ("# " + "x" * 200 + "\n\nBody", "heading_overhead"),
        ("# Help", "empty_document"),
    ],
)
def test_unprocessable_source_fails_explicitly(body, code):
    with pytest.raises(ProcessingError, match=code):
        TokenAwareChunker().chunks(snapshot(body), config(), CharacterEncoder())


def test_document_budgets():
    with pytest.raises(ProcessingError, match="document_budget"):
        TokenAwareChunker().chunks(
            snapshot("# Help\n\n" + "x" * 500),
            config(max_document_chunks=1),
            CharacterEncoder(),
        )
    with pytest.raises(ProcessingError, match="document_budget"):
        TokenAwareChunker().chunks(
            snapshot("# Help\n\n" + "x" * 500),
            config(max_document_tokens=100),
            CharacterEncoder(),
        )


@pytest.mark.parametrize(
    "vectors",
    [
        [],
        [[0, 0, 0]],
        [[1, 0]],
        [[float("nan"), 0, 0]],
        [[float("inf"), 0, 0]],
        [[2, 0, 0]],
        [[1, 0, 0], [1, 0, 0]],
    ],
)
def test_vectors_reject_incomplete_or_invalid_outputs(vectors):
    with pytest.raises(ProcessingError):
        validate_vectors(vectors, 1, 3)


def test_normalized_vectors_are_accepted():
    validate_vectors([[0.6, 0.8, 0.0]], 1, 3)


@pytest.mark.parametrize(
    "body",
    [
        "a" * 89 + "   " + "b" * 50,
        "a" * 92 + "\u2003\t" + "b" * 50,
        "a" * 89 + "   \n    " + "b" * 50,
    ],
)
def test_character_preparation_preserves_spaces_at_split_boundaries(body):
    chunks = TokenAwareChunker().chunks(
        snapshot("# Help\n\n" + body), config(target_chars=100), CharacterEncoder()
    )
    assert "".join(chunk["text"].removeprefix("# Help\n\n") for chunk in chunks) == body
