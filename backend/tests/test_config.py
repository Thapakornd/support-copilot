from uuid import UUID

import pytest
from pydantic import ValidationError

from support_copilot.core.config import Settings, WorkerSettings


def worker_values():
    return {
        "model_id": UUID("00000000-0000-0000-0000-000000000001"),
        "model_name": "test/model",
        "model_revision": "a" * 40,
        "dimensions": 3,
        "tokenizer_limit": 128,
        "document_prompt": "",
        "query_prompt": "",
    }


def test_shared_database_from_dotenv_is_used_by_worker(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EMBEDDING_DATABASE_URL", raising=False)
    env = tmp_path / ".env"
    env.write_text("DATABASE_URL=postgresql://shared:secret@db/shared\n")
    settings = WorkerSettings(_env_file=env, **worker_values())
    assert (
        settings.database_url.get_secret_value()
        == "postgresql://shared:secret@db/shared"
    )
    assert "secret" not in repr(settings)


def test_worker_database_override_and_process_environment_take_precedence(
    tmp_path, monkeypatch
):
    env = tmp_path / ".env"
    env.write_text(
        "DATABASE_URL=postgresql://shared/db\n"
        "EMBEDDING_DATABASE_URL=postgresql://file-worker/db\n"
    )
    monkeypatch.setenv("EMBEDDING_DATABASE_URL", "postgresql://process-worker/db")
    assert (
        WorkerSettings(_env_file=env, **worker_values()).database_url.get_secret_value()
        == "postgresql://process-worker/db"
    )


def test_runtime_settings_from_dotenv(tmp_path, monkeypatch):
    for name in (
        "DATABASE_URL",
        "ANTHROPIC_API_KEY",
        "LLM_MODEL",
        "API_HOST",
        "API_PORT",
        "API_RELOAD",
        "CORS_ORIGINS",
    ):
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "DATABASE_URL=postgresql://app:password@db/app\n"
        "ANTHROPIC_API_KEY=test-key\n"
        "LLM_MODEL=test-model\n"
        "API_HOST=0.0.0.0\nAPI_PORT=8123\nAPI_RELOAD=false\n"
        'CORS_ORIGINS=["https://support.example"]\n'
    )
    settings = Settings(_env_file=env)
    assert (
        settings.database_url.get_secret_value() == "postgresql://app:password@db/app"
    )
    assert settings.anthropic_api_key.get_secret_value() == "test-key"
    assert settings.llm_model == "test-model"
    assert (settings.api_host, settings.api_port, settings.api_reload) == (
        "0.0.0.0",
        8123,
        False,
    )
    assert settings.cors_origins == ["https://support.example"]
    assert "password" not in repr(settings)
    assert "test-key" not in repr(settings)


@pytest.mark.parametrize("url", ["", "   ", "https://example.test"])
def test_worker_rejects_missing_or_non_postgres_database(url):
    with pytest.raises(ValidationError):
        WorkerSettings(_env_file=None, database_url=url, **worker_values())
