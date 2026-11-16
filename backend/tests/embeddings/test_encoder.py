import sys
from types import SimpleNamespace

import pytest
from support_copilot.domain.embedding_job import ProcessingError
from support_copilot.infrastructure.embeddings.sentence_transformer import (
    SentenceTransformerEncoder,
)
from test_processing import config


def test_pinned_offline_encoder_counts_prompts_once_and_reuses_model(monkeypatch):
    calls = []

    class Model:
        max_seq_length = 128

        def __init__(self, name, **kwargs):
            calls.append((name, kwargs))

        def get_sentence_embedding_dimension(self):
            return 3

        def tokenizer(self, text, **kwargs):
            assert kwargs == {"add_special_tokens": True, "truncation": False}
            return {"input_ids": list(range(len(text) + 2))}

        def encode_document(self, texts, **kwargs):
            assert kwargs["prompt"] == "p: "
            assert texts == ["body"]
            return SimpleNamespace(tolist=lambda: [[1.0, 0.0, 0.0]])

        def encode_query(self, texts, **kwargs):
            assert kwargs["prompt"] == "q: "
            return SimpleNamespace(tolist=lambda: [[0.0, 1.0, 0.0]])

    monkeypatch.setitem(
        sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=Model)
    )
    encoder = SentenceTransformerEncoder(config())
    assert calls == []
    assert encoder.token_count("body") == 9
    assert encoder.encode_documents(["body"]) == [[1.0, 0.0, 0.0]]
    assert encoder.encode_queries(["ask"]) == [[0.0, 1.0, 0.0]]
    assert len(calls) == 1
    assert calls[0][1]["revision"] == "a" * 40
    assert calls[0][1]["local_files_only"] is True
    assert calls[0][1]["trust_remote_code"] is False
    with pytest.raises(ProcessingError, match="oversized_block"):
        encoder.encode_documents(["x" * 100])


def test_missing_offline_model_returns_safe_actionable_code(monkeypatch):
    def missing(*args, **kwargs):
        raise OSError("credential and body should never escape")

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=missing),
    )
    with pytest.raises(ProcessingError, match="^model_unavailable$"):
        SentenceTransformerEncoder(config()).token_count("body")
