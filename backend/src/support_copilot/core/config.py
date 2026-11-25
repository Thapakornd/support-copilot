from pathlib import Path
from uuid import UUID

from psycopg import ProgrammingError
from psycopg.conninfo import make_conninfo
from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from support_copilot.domain.embedding_job import EmbeddingConfig

BACKEND_DIR = Path(__file__).resolve().parents[3]
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )

    database_url: SecretStr = SecretStr("")
    llm_model: str = ""
    llm_provider: str = "anthropic"
    llm_timeout_seconds: float = Field(default=30, gt=0, allow_inf_nan=False)
    anthropic_api_key: SecretStr = SecretStr("")
    openrouter_api_key: SecretStr = SecretStr("")
    chat_candidate_limit: int = Field(default=20, gt=0)
    chat_max_distance: float = Field(default=0.5, ge=0, le=2)
    chat_max_passages: int = Field(default=6, gt=0)
    chat_evidence_char_limit: int = Field(default=12000, gt=0)
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    api_reload: bool = False
    cors_origins: list[str] = []
    # Impersonation by header: only for local demos, never on a reachable host.
    demo_auth: bool = False

    @model_validator(mode="after")
    def demo_auth_stays_local(self):
        if self.demo_auth and self.api_host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("DEMO_AUTH requires API_HOST to be a loopback address")
        return self


settings = Settings()


class EmbeddingSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="EMBEDDING_",
        populate_by_name=True,
    )

    model_id: UUID
    model_name: str = Field(min_length=1)
    model_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    dimensions: int = Field(gt=0)
    tokenizer_limit: int = Field(gt=0)
    document_prompt: str
    query_prompt: str
    batch_size: int = Field(default=32, gt=0)
    max_document_tokens: int = Field(default=100000, gt=0)
    max_document_chunks: int = Field(default=2000, gt=0)
    target_chars: int = Field(default=2400, ge=100)
    device: str = "cpu"
    offline: bool = True

    def effective_config(self) -> EmbeddingConfig:
        return EmbeddingConfig(
            self.model_id,
            self.model_name,
            self.model_revision,
            self.dimensions,
            self.tokenizer_limit,
            self.document_prompt,
            self.query_prompt,
            target_chars=self.target_chars,
            max_document_tokens=self.max_document_tokens,
            max_document_chunks=self.max_document_chunks,
        )


class WorkerSettings(EmbeddingSettings):
    database_url: SecretStr = Field(
        validation_alias=AliasChoices("EMBEDDING_DATABASE_URL", "DATABASE_URL")
    )
    lease_seconds: int = Field(default=300, gt=0)
    heartbeat_seconds: float = Field(default=60, gt=0)
    max_attempts: int = Field(default=3, gt=0)

    @model_validator(mode="after")
    def valid_lease(self):
        if self.heartbeat_seconds >= self.lease_seconds:
            raise ValueError("Heartbeat must be shorter than lease")
        if not self.database_url.get_secret_value().strip():
            raise ValueError("Database URL is required")
        try:
            make_conninfo(self.database_url.get_secret_value())
        except ProgrammingError:
            raise ValueError("Invalid PostgreSQL connection configuration") from None
        return self
