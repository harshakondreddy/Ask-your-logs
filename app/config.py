from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    elasticsearch_url: str = Field(
        default="http://elasticsearch.logging.svc.cluster.local:9200",
        alias="ELASTICSEARCH_URL",
    )
    elasticsearch_username: str | None = Field(default=None, alias="ELASTICSEARCH_USERNAME")
    elasticsearch_password: str | None = Field(default=None, alias="ELASTICSEARCH_PASSWORD")
    elasticsearch_index: str = Field(default="logs-*", alias="ELASTICSEARCH_INDEX")
    elasticsearch_verify_certs: bool = Field(default=True, alias="ELASTICSEARCH_VERIFY_CERTS")
    elasticsearch_ca_cert_path: str | None = Field(default=None, alias="ELASTICSEARCH_CA_CERT_PATH")
    timestamp_field: str = Field(default="@timestamp", alias="ELASTICSEARCH_TIMESTAMP_FIELD")
    # --- LLM provider selection ---
    # Valid values: gemini | openai | azure_openai | ollama
    llm_provider: str = Field(default="gemini", alias="LLM_PROVIDER")

    # Google Gemini
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-flash-latest", alias="GEMINI_MODEL")

    # OpenAI
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

    # Azure OpenAI
    azure_openai_api_key: str | None = Field(default=None, alias="AZURE_OPENAI_API_KEY")
    azure_openai_endpoint: str | None = Field(default=None, alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_deployment: str | None = Field(default=None, alias="AZURE_OPENAI_DEPLOYMENT")
    azure_openai_api_version: str = Field(default="2024-02-01", alias="AZURE_OPENAI_API_VERSION")

    # Ollama
    ollama_base_url: str = Field(default="http://127.0.0.1:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="gemma3:4b", alias="OLLAMA_MODEL")
    ollama_timeout_seconds: int = Field(default=600, alias="OLLAMA_TIMEOUT_SECONDS")

    # Shared key required in the X-API-Key header on /ask. Unset = no auth (local use only).
    api_key: str | None = Field(default=None, alias="API_KEY")

    max_logs_limit: int = Field(default=330, alias="MAX_LOGS_LIMIT")
    request_timeout_seconds: int = Field(default=30, alias="REQUEST_TIMEOUT_SECONDS")


@lru_cache
def get_settings() -> Settings:
    return Settings()
