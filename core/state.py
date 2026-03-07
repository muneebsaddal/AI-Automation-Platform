from typing import Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime


class ExecutionLog(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    agent: str
    level: Literal["info", "warning", "error"]
    message: str


class ValidationError(BaseModel):
    field: str
    issue: str
    value: Any = None


class AgentState(BaseModel):
    # Input
    run_id: str
    raw_input: str

    # Pipeline state
    plan: list[str] = Field(default_factory=list)
    execution_results: list[dict] = Field(default_factory=list)
    structured_output: dict = Field(default_factory=dict)
    validation_errors: list[ValidationError] = Field(default_factory=list)

    # Observability
    logs: list[ExecutionLog] = Field(default_factory=list)
    current_agent: str = ""
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    retry_count: int = 0
    max_retries: int = 2

    # Trace metadata
    started_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: str = ""
    error: str = ""

    def add_log(self, agent: str, message: str, level: str = "info") -> None:
        self.logs.append(ExecutionLog(agent=agent, level=level, message=message))

    def to_trace(self) -> dict:
        """Export full execution trace as JSON-serialisable dict."""
        return self.model_dump()
