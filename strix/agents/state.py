import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def _generate_agent_id() -> str:
    return f"agent_{uuid.uuid4().hex[:8]}"


class AgentStatus(Enum):
    """Explicit agent status - single source of truth for agent state."""

    RUNNING = "running"
    WAITING_FOR_MESSAGE = "waiting_for_message"
    WAITING_FOR_RECOVERY = "waiting_for_recovery"  # LLM retry pending
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class AgentState(BaseModel):
    agent_id: str = Field(default_factory=_generate_agent_id)
    agent_name: str = "Strix Agent"
    agent_role: str | None = None
    parent_id: str | None = None
    sandbox_id: str | None = None
    sandbox_token: str | None = None
    sandbox_info: dict[str, Any] | None = None

    task: str = ""
    iteration: int = 0
    max_iterations: int = 300
    max_wait_seconds: int = 300  # 5 minutes default, always-on timeout

    # Single status field replaces: completed, stop_requested, waiting_for_input, llm_failed
    status: AgentStatus = AgentStatus.RUNNING
    waiting_start_time: datetime | None = None
    final_result: dict[str, Any] | None = None
    failure_reason: str | None = None  # Reason for FAILED status
    max_iterations_warning_sent: bool = False
    consecutive_empty_responses: int = 0  # Track empty LLM responses

    messages: list[dict[str, Any]] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)

    start_time: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    last_updated: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    actions_taken: list[dict[str, Any]] = Field(default_factory=list)
    observations: list[dict[str, Any]] = Field(default_factory=list)

    errors: list[str] = Field(default_factory=list)

    def increment_iteration(self) -> None:
        self.iteration += 1
        self.last_updated = datetime.now(UTC).isoformat()

    def add_message(self, role: str, content: Any) -> None:
        self.messages.append({"role": role, "content": content})
        self.last_updated = datetime.now(UTC).isoformat()

    def add_action(self, action: dict[str, Any]) -> None:
        self.actions_taken.append(
            {
                "iteration": self.iteration,
                "timestamp": datetime.now(UTC).isoformat(),
                "action": action,
            }
        )

    def add_observation(self, observation: dict[str, Any]) -> None:
        self.observations.append(
            {
                "iteration": self.iteration,
                "timestamp": datetime.now(UTC).isoformat(),
                "observation": observation,
            }
        )

    def add_error(self, error: str) -> None:
        self.errors.append(f"Iteration {self.iteration}: {error}")
        self.last_updated = datetime.now(UTC).isoformat()

    def update_context(self, key: str, value: Any) -> None:
        self.context[key] = value
        self.last_updated = datetime.now(UTC).isoformat()

    def set_completed(self, final_result: dict[str, Any] | None = None) -> None:
        self.status = AgentStatus.COMPLETED
        self.final_result = final_result
        self.waiting_start_time = None
        self.last_updated = datetime.now(UTC).isoformat()

    def set_failed(self, reason: str) -> None:
        """Mark agent as failed with a reason."""
        self.status = AgentStatus.FAILED
        self.failure_reason = reason
        self.waiting_start_time = None
        self.last_updated = datetime.now(UTC).isoformat()

    def request_stop(self) -> None:
        self.status = AgentStatus.STOPPED
        self.waiting_start_time = None
        self.last_updated = datetime.now(UTC).isoformat()

    def should_stop(self) -> bool:
        """Check if agent should exit its loop."""
        return (
            self.status in (AgentStatus.COMPLETED, AgentStatus.FAILED, AgentStatus.STOPPED)
            or self.has_reached_max_iterations()
        )

    def is_waiting_for_input(self) -> bool:
        return self.status in (AgentStatus.WAITING_FOR_MESSAGE, AgentStatus.WAITING_FOR_RECOVERY)

    def enter_waiting_state(self, llm_failed: bool = False) -> None:
        if llm_failed:
            self.status = AgentStatus.WAITING_FOR_RECOVERY
        else:
            self.status = AgentStatus.WAITING_FOR_MESSAGE
        self.waiting_start_time = datetime.now(UTC)
        self.last_updated = datetime.now(UTC).isoformat()

    def resume_from_waiting(self, new_task: str | None = None) -> None:
        self.status = AgentStatus.RUNNING
        self.waiting_start_time = None
        self.failure_reason = None
        self.consecutive_empty_responses = 0
        if new_task:
            self.task = new_task
        self.last_updated = datetime.now(UTC).isoformat()

    def has_reached_max_iterations(self) -> bool:
        return self.iteration >= self.max_iterations

    def is_approaching_max_iterations(self, threshold: float = 0.85) -> bool:
        return self.iteration >= int(self.max_iterations * threshold)

    def has_waiting_timeout(self) -> bool:
        """Check if waiting state has exceeded max_wait_seconds. Always-on timeout."""
        if not self.is_waiting_for_input() or not self.waiting_start_time:
            return False

        elapsed = (datetime.now(UTC) - self.waiting_start_time).total_seconds()
        return elapsed > self.max_wait_seconds

    # Backward compatibility properties
    @property
    def completed(self) -> bool:
        return self.status == AgentStatus.COMPLETED

    @property
    def stop_requested(self) -> bool:
        return self.status == AgentStatus.STOPPED

    @property
    def waiting_for_input(self) -> bool:
        return self.is_waiting_for_input()

    @property
    def llm_failed(self) -> bool:
        return self.status == AgentStatus.WAITING_FOR_RECOVERY

    def has_empty_last_messages(self, count: int = 3) -> bool:
        if len(self.messages) < count:
            return False

        last_messages = self.messages[-count:]

        for message in last_messages:
            content = message.get("content", "")
            if isinstance(content, str) and content.strip():
                return False

        return True

    def get_conversation_history(self) -> list[dict[str, Any]]:
        return self.messages

    def get_execution_summary(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "parent_id": self.parent_id,
            "sandbox_id": self.sandbox_id,
            "sandbox_info": self.sandbox_info,
            "task": self.task,
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "status": self.status.value,
            "completed": self.completed,
            "failure_reason": self.failure_reason,
            "final_result": self.final_result,
            "start_time": self.start_time,
            "last_updated": self.last_updated,
            "total_actions": len(self.actions_taken),
            "total_observations": len(self.observations),
            "total_errors": len(self.errors),
            "has_errors": len(self.errors) > 0,
            "max_iterations_reached": self.has_reached_max_iterations() and not self.completed,
        }
