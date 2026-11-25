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


def test_query_embedding_settings_share_the_worker_configuration_without_worker_credentials(
    tmp_path, monkeypatch
):
    from support_copilot.core.config import EmbeddingSettings

    monkeypatch.setenv("EMBEDDING_DATABASE_URL", "not a PostgreSQL DSN")
    monkeypatch.setenv("EMBEDDING_HEARTBEAT_SECONDS", "999")
    env = tmp_path / ".env"
    env.write_text("EMBEDDING_QUERY_PROMPT='query: '\nEMBEDDING_TARGET_CHARS=750\n")
    values = worker_values()
    del values["query_prompt"]
    query = EmbeddingSettings(_env_file=env, **values)
    worker = WorkerSettings(
        _env_file=env,
        database_url="postgresql://db/worker",
        heartbeat_seconds=45,
        **values,
    )
    assert query.effective_config().config_hash == worker.effective_config().config_hash
    assert query.effective_config().query_prompt == "query: "
    assert query.effective_config().target_chars == 750


@pytest.mark.parametrize(
    "values",
    [
        {"llm_timeout_seconds": 0},
        {"chat_candidate_limit": 0},
        {"chat_max_distance": 2.1},
        {"chat_max_passages": 0},
        {"chat_evidence_char_limit": 0},
    ],
)
def test_runtime_rejects_invalid_chat_limits(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_demo_auth_defaults_off_and_requires_a_loopback_host():
    assert Settings(_env_file=None).demo_auth is False
    for host in ("127.0.0.1", "localhost", "::1"):
        assert Settings(_env_file=None, demo_auth=True, api_host=host).demo_auth
    with pytest.raises(ValidationError):
        Settings(_env_file=None, demo_auth=True, api_host="0.0.0.0")
    assert Settings(_env_file=None, api_host="0.0.0.0").demo_auth is False
