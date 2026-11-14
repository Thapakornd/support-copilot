from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_model: str = "claude-sonnet-5-5"
    anthropic_api_key: str = ""


settings = Settings()
