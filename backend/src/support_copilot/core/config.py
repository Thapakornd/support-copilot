from uuid import UUID

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from support_copilot.domain.embedding_job import EmbeddingConfig


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_model: str = "claude-sonnet-5-5"
    anthropic_api_key: str = ""


settings = Settings()


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", env_prefix="EMBEDDING_"
    )

    database_url: SecretStr
    model_id: UUID
    model_name: str = Field(min_length=1)
    model_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    dimensions: int = Field(gt=0)
    tokenizer_limit: int = Field(gt=0)
    document_prompt: str
    query_prompt: str
    lease_seconds: int = Field(default=300, gt=0)
    heartbeat_seconds: float = Field(default=60, gt=0)
    max_attempts: int = Field(default=3, gt=0)
    batch_size: int = Field(default=32, gt=0)
    max_document_tokens: int = Field(default=100000, gt=0)
    max_document_chunks: int = Field(default=2000, gt=0)
    target_chars: int = Field(default=2400, ge=100)
    device: str = "cpu"
    offline: bool = True

    @model_validator(mode="after")
    def valid_lease(self):
        if self.heartbeat_seconds >= self.lease_seconds:
            raise ValueError("Heartbeat must be shorter than lease")
        if not self.database_url.get_secret_value().strip():
            raise ValueError("Database URL is required")
        return self

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
