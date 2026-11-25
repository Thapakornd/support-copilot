"""Exercise a published passage through HTTP and the Anthropic wire adapter."""

import json
from unittest.mock import patch

import httpx2
from fastapi.testclient import TestClient
from pydantic import SecretStr
from test_embedding_admission import stage
from test_embedding_publication import chunks

from support_copilot.core.config import settings
from support_copilot.infrastructure.embeddings.sentence_transformer import (
    SentenceTransformerEncoder,
)
from support_copilot.infrastructure.postgres.knowledge_repository import (
    KnowledgeRepository,
)
from support_copilot.interface.api.main import app
from support_copilot.interface.api.routes.chat import get_answer_question


def test_published_passage_reaches_model_and_returns_as_http_citation(
    db, config, monkeypatch
):
    text = "Check the network peering status."
    stage(db, text)
    store = KnowledgeRepository(db)
    store.admit(config, ["doc-1"])
    job = store.claim(config.config_hash, store.now())
    store.publish(job, chunks(text), [[1, 0, 0]])

    for field in (
        "model_id",
        "model_name",
        "model_revision",
        "dimensions",
        "tokenizer_limit",
        "query_prompt",
        "document_prompt",
        "target_chars",
        "max_document_tokens",
        "max_document_chunks",
    ):
        monkeypatch.setenv("EMBEDDING_" + field.upper(), str(getattr(config, field)))
    monkeypatch.setattr(settings, "database_url", SecretStr(db))
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "llm_model", "test-model")
    monkeypatch.setattr(settings, "anthropic_api_key", SecretStr("fixture-key"))
    monkeypatch.setenv("ANTHROPIC_API_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://127.0.0.1:1")
    monkeypatch.setattr(SentenceTransformerEncoder, "token_count", lambda *a, **kw: 5)
    monkeypatch.setattr(
        SentenceTransformerEncoder, "encode_queries", lambda *a: [[1, 0, 0]]
    )

    def provider(request):
        payload = json.loads(request.content)
        assert text in str(payload["messages"])
        tool_name = payload["tools"][0]["name"]
        return httpx2.Response(
            200,
            json={
                "id": "msg_fixture",
                "model": "test-model",
                "type": "message",
                "role": "assistant",
                "stop_reason": "tool_use",
                "stop_sequence": None,
                "usage": {"input_tokens": 50, "output_tokens": 12},
                "content": [
                    {
                        "type": "tool_use",
                        "name": tool_name,
                        "id": "tool_1",
                        "input": {
                            "status": "answered",
                            "steps": [{"text": text, "source_ids": ["S1"]}],
                        },
                    }
                ],
            },
            request=request,
        )

    get_answer_question.cache_clear()
    try:
        with patch.object(httpx2.HTTPTransport, "handle_request", side_effect=provider):
            response = TestClient(app).post(
                "/chat",
                json={
                    "question": "What peering setting should I check?",
                    "category": "Connectivity",
                },
            )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["status"] == "answered"
        assert result["answer"] == text + " [1]"
        [source] = result["sources"]
        assert (
            source["number"],
            source["revision_id"],
            source["chunk_id"],
            source["source_url"],
        ) == (1, str(job.revision_id), "chunk_1", "https://example.org/help")
    finally:
        get_answer_question.cache_clear()
