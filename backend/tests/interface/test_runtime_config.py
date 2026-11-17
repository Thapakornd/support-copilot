from unittest.mock import patch

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


def test_chat_passes_dotenv_credentials_to_provider_without_process_key(monkeypatch):
    from pydantic import SecretStr

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(settings, "llm_model", "configured-model")
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", SecretStr("dotenv-only-key"))
    with patch("support_copilot.infrastructure.langchain.llm.init_chat_model") as init:
        init.return_value.invoke.return_value.text = "Provider response"
        assert build_answer_question()("Hello").text == "Provider response"
    init.assert_called_once_with(
        "configured-model",
        model_provider="anthropic",
        api_key="dotenv-only-key",
    )
