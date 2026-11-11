from pydantic import BaseModel, Field, field_validator


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Question to ask about the logs")
    namespace: str | None = Field(default=None, description="Kubernetes namespace filter")
    app: str | None = Field(default=None, description="Application, pod, or container filter")
    minutes: int = Field(default=30, ge=1, le=1440, description="Time window in minutes")
    max_logs: int = Field(default=150, ge=1, description="Maximum number of logs to use")

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question must not be empty")
        return stripped

    @field_validator("namespace", "app")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class HealthResponse(BaseModel):
    status: str = "ok"


class AskResponse(BaseModel):
    answer: str
    logs_used: int
    time_window_minutes: int
    namespace: str | None = None
    app: str | None = None
    elasticsearch_index: str
    llm_provider: str | None = None


class LogEntry(BaseModel):
    timestamp: str | None = None
    component_name: str | None = None
    component_log_level: str | None = None
    component_class: str | None = None
    hostname: str | None = None
    site_id: str | None = None
    message: str

    def to_prompt_line(self) -> str:
        parts = [
            f"timestamp={self.timestamp or 'unknown'}",
            f"service={self.component_name or 'unknown'}",
            f"level={self.component_log_level or 'unknown'}",
            f"class={self.component_class or 'unknown'}",
            f"host={self.hostname or 'unknown'}",
            f"site={self.site_id or 'unknown'}",
            f"message={self.message}",
        ]
        return " | ".join(parts)
