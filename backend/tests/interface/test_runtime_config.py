from unittest.mock import Mock, patch

import pytest

from support_copilot import main
from support_copilot.bootstrap import build_answer_question
from support_copilot.core.config import settings


def test_launcher_uses_configured_bind_and_reload(monkeypatch):
    monkeypatch.setattr(settings, "api_host", "0.0.0.0")
    monkeypatch.setattr(settings, "api_port", 8123)
    monkeypatch.setattr(settings, "api_reload", False)
    with patch("uvicorn.run") as run:
        main()
    run.assert_called_once_with(
        "support_copilot.interface.api.main:app",
        host="0.0.0.0",
        port=8123,
        reload=False,
    )


@pytest.mark.parametrize(
    ("provider", "model", "expected_key"),
    [
        ("anthropic", "configured-model", "anthropic-key"),
        ("openrouter", "anthropic/configured-model", "openrouter-key"),
    ],
)
def test_chat_uses_api_database_credentials_and_explicit_model_timeout(
    monkeypatch, provider, model, expected_key
):
    from pydantic import SecretStr

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(settings, "llm_model", model)
    monkeypatch.setattr(settings, "llm_provider", provider)
    monkeypatch.setattr(
        settings, "database_url", SecretStr("postgresql://reader@db/api")
    )
    monkeypatch.setattr(settings, "anthropic_api_key", SecretStr("anthropic-key"))
    monkeypatch.setattr(settings, "openrouter_api_key", SecretStr("openrouter-key"))
    monkeypatch.setattr(settings, "llm_timeout_seconds", 19)
    monkeypatch.setenv("EMBEDDING_DATABASE_URL", "postgresql://worker@db/api")
    for key, value in {
        "MODEL_ID": "00000000-0000-0000-0000-000000000001",
        "MODEL_NAME": "test/model",
        "MODEL_REVISION": "a" * 40,
        "DIMENSIONS": "3",
        "TOKENIZER_LIMIT": "128",
        "DOCUMENT_PROMPT": "passage: ",
        "QUERY_PROMPT": "query: ",
    }.items():
        monkeypatch.setenv(f"EMBEDDING_{key}", value)

    create_llm = Mock()
    create_retriever = Mock()
    create_encoder = Mock()
    monkeypatch.setattr("support_copilot.bootstrap.LangChainLLM", create_llm)
    monkeypatch.setattr(
        "support_copilot.infrastructure.embeddings.sentence_transformer.SentenceTransformerEncoder",
        create_encoder,
    )
    monkeypatch.setattr(
        "support_copilot.infrastructure.postgres.retrieval.PostgresRetriever",
        create_retriever,
    )
    build_answer_question()

    dsn, config = create_retriever.call_args.args
    assert dsn == "postgresql://reader@db/api"
    assert config.query_prompt == "query: "
    assert create_encoder.call_args.args == (config,)
    create_retriever.return_value.validate_configuration.assert_called_once_with()
    create_llm.assert_called_once_with(
        model,
        provider=provider,
        api_key=expected_key,
        timeout=19,
    )
