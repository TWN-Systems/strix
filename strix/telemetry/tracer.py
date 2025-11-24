import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional
from uuid import uuid4


if TYPE_CHECKING:
    from collections.abc import Callable


logger = logging.getLogger(__name__)

_global_tracer: Optional["Tracer"] = None


def get_global_tracer() -> Optional["Tracer"]:
    return _global_tracer


def set_global_tracer(tracer: "Tracer") -> None:
    global _global_tracer  # noqa: PLW0603
    _global_tracer = tracer


class EventType(str, Enum):
    """Types of events that can be emitted by the tracer."""

    # Scan lifecycle events
    SCAN_START = "scan_start"
    SCAN_END = "scan_end"
    SCAN_ERROR = "scan_error"

    # Agent lifecycle events
    AGENT_CREATED = "agent_created"
    AGENT_ITERATION = "agent_iteration"
    AGENT_COMPLETED = "agent_completed"
    AGENT_ERROR = "agent_error"

    # LLM events
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    LLM_ERROR = "llm_error"

    # Tool events
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"
    TOOL_ERROR = "tool_error"

    # Vulnerability events
    VULNERABILITY_FOUND = "vulnerability_found"
    VULNERABILITY_VERIFIED = "vulnerability_verified"

    # Progress events
    PROGRESS_UPDATE = "progress_update"
    PHASE_CHANGE = "phase_change"

    # Scope events
    SCOPE_LOADED = "scope_loaded"
    SCOPE_TARGET_START = "scope_target_start"
    SCOPE_TARGET_END = "scope_target_end"


@dataclass
class TracerEvent:
    """A single event in the tracer event stream."""

    event_id: str
    event_type: EventType
    timestamp: str
    agent_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "agent_id": self.agent_id,
            "data": self.data,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        """Convert event to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TracerEvent":
        """Create event from dictionary."""
        return cls(
            event_id=data["event_id"],
            event_type=EventType(data["event_type"]),
            timestamp=data["timestamp"],
            agent_id=data.get("agent_id"),
            data=data.get("data", {}),
            metadata=data.get("metadata", {}),
        )


class Tracer:
    def __init__(self, run_name: str | None = None):
        self.run_name = run_name
        self.run_id = run_name or f"run-{uuid4().hex[:8]}"
        self.start_time = datetime.now(UTC).isoformat()
        self.end_time: str | None = None

        self.agents: dict[str, dict[str, Any]] = {}
        self.tool_executions: dict[int, dict[str, Any]] = {}
        self.chat_messages: list[dict[str, Any]] = []

        self.vulnerability_reports: list[dict[str, Any]] = []
        self.final_scan_result: str | None = None

        self.scan_results: dict[str, Any] | None = None
        self.scan_config: dict[str, Any] | None = None
        self.scope_context: dict[str, Any] | None = None
        self.run_metadata: dict[str, Any] = {
            "run_id": self.run_id,
            "run_name": self.run_name,
            "start_time": self.start_time,
            "end_time": None,
            "targets": [],
            "status": "running",
        }
        self._run_dir: Path | None = None
        self._next_execution_id = 1
        self._next_message_id = 1
        self._next_event_id = 1
        self._saved_vuln_ids: set[str] = set()

        # Event streaming
        self._events: list[TracerEvent] = []
        self._event_cursor: int = 0
        self._event_callbacks: list[Callable[[TracerEvent], None]] = []
        self._events_file: Path | None = None

        self.vulnerability_found_callback: Callable[[str, str, str, str], None] | None = None

    def add_event_callback(self, callback: Callable[[TracerEvent], None]) -> None:
        """Add a callback to be invoked for each new event."""
        self._event_callbacks.append(callback)

    def remove_event_callback(self, callback: Callable[[TracerEvent], None]) -> None:
        """Remove an event callback."""
        if callback in self._event_callbacks:
            self._event_callbacks.remove(callback)

    def _emit_event(
        self,
        event_type: EventType,
        agent_id: str | None = None,
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TracerEvent:
        """Emit a new event to the event stream."""
        event_id = f"evt-{self._next_event_id:06d}"
        self._next_event_id += 1

        event = TracerEvent(
            event_id=event_id,
            event_type=event_type,
            timestamp=datetime.now(UTC).isoformat(),
            agent_id=agent_id,
            data=data or {},
            metadata=metadata or {},
        )

        self._events.append(event)

        # Invoke callbacks
        for callback in self._event_callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.warning(f"Event callback error: {e}")

        # Persist to JSONL file
        self._persist_event(event)

        return event

    def _persist_event(self, event: TracerEvent) -> None:
        """Persist event to JSONL file."""
        try:
            if self._events_file is None:
                run_dir = self.get_run_dir()
                self._events_file = run_dir / "events.jsonl"

            with self._events_file.open("a", encoding="utf-8") as f:
                f.write(event.to_json() + "\n")
        except (OSError, RuntimeError) as e:
            logger.warning(f"Failed to persist event: {e}")

    def get_events(self, since_cursor: int | None = None) -> list[TracerEvent]:
        """Get events, optionally since a cursor position."""
        if since_cursor is None:
            return self._events.copy()
        return self._events[since_cursor:]

    def get_event_cursor(self) -> int:
        """Get the current event cursor position."""
        return len(self._events)

    def get_events_by_type(self, event_type: EventType) -> list[TracerEvent]:
        """Get all events of a specific type."""
        return [e for e in self._events if e.event_type == event_type]

    def get_events_by_agent(self, agent_id: str) -> list[TracerEvent]:
        """Get all events for a specific agent."""
        return [e for e in self._events if e.agent_id == agent_id]

    def log_scan_start(self, config: dict[str, Any]) -> None:
        """Log scan start event."""
        self._emit_event(
            EventType.SCAN_START,
            data={
                "run_id": self.run_id,
                "config": config,
            },
        )

    def log_scan_end(self, success: bool = True, error: str | None = None) -> None:
        """Log scan end event."""
        self._emit_event(
            EventType.SCAN_END,
            data={
                "success": success,
                "error": error,
                "vulnerabilities_found": len(self.vulnerability_reports),
            },
        )

    def log_agent_iteration(
        self,
        agent_id: str,
        iteration: int,
        action: str | None = None,
    ) -> None:
        """Log an agent iteration event."""
        self._emit_event(
            EventType.AGENT_ITERATION,
            agent_id=agent_id,
            data={
                "iteration": iteration,
                "action": action,
            },
        )

    def log_llm_request(
        self,
        agent_id: str,
        model: str,
        messages_count: int,
        tokens_estimate: int | None = None,
    ) -> str:
        """Log an LLM request event. Returns event_id for correlation."""
        event = self._emit_event(
            EventType.LLM_REQUEST,
            agent_id=agent_id,
            data={
                "model": model,
                "messages_count": messages_count,
                "tokens_estimate": tokens_estimate,
            },
        )
        return event.event_id

    def log_llm_response(
        self,
        agent_id: str,
        request_event_id: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
        duration_ms: int | None = None,
    ) -> None:
        """Log an LLM response event."""
        self._emit_event(
            EventType.LLM_RESPONSE,
            agent_id=agent_id,
            data={
                "request_event_id": request_event_id,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cached_tokens": cached_tokens,
                "duration_ms": duration_ms,
            },
        )

    def log_tool_event(
        self,
        event_type: EventType,
        agent_id: str,
        tool_name: str,
        execution_id: int | None = None,
        args: dict[str, Any] | None = None,
        result: Any | None = None,
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Log a tool-related event."""
        self._emit_event(
            event_type,
            agent_id=agent_id,
            data={
                "tool_name": tool_name,
                "execution_id": execution_id,
                "args": args,
                "result": result if result is not None else None,
                "error": error,
                "duration_ms": duration_ms,
            },
        )

    def log_scope_loaded(self, scope_context: dict[str, Any]) -> None:
        """Log scope loaded event."""
        self.scope_context = scope_context
        self._emit_event(
            EventType.SCOPE_LOADED,
            data={
                "engagement_name": scope_context.get("metadata", {}).get("engagement_name"),
                "targets_count": len(scope_context.get("targets", [])),
                "networks_count": len(scope_context.get("networks", [])),
            },
        )

    def log_progress_update(
        self,
        agent_id: str | None,
        phase: str,
        progress: float,
        message: str | None = None,
    ) -> None:
        """Log a progress update event."""
        self._emit_event(
            EventType.PROGRESS_UPDATE,
            agent_id=agent_id,
            data={
                "phase": phase,
                "progress": progress,
                "message": message,
            },
        )

    def set_run_name(self, run_name: str) -> None:
        self.run_name = run_name
        self.run_id = run_name

    def get_run_dir(self) -> Path:
        if self._run_dir is None:
            runs_dir = Path.cwd() / "strix_runs"
            runs_dir.mkdir(exist_ok=True)

            run_dir_name = self.run_name if self.run_name else self.run_id
            self._run_dir = runs_dir / run_dir_name
            self._run_dir.mkdir(exist_ok=True)

        return self._run_dir

    def add_vulnerability_report(
        self,
        title: str,
        content: str,
        severity: str,
    ) -> str:
        report_id = f"vuln-{len(self.vulnerability_reports) + 1:04d}"

        report = {
            "id": report_id,
            "title": title.strip(),
            "content": content.strip(),
            "severity": severity.lower().strip(),
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        }

        self.vulnerability_reports.append(report)
        logger.info(f"Added vulnerability report: {report_id} - {title}")

        if self.vulnerability_found_callback:
            self.vulnerability_found_callback(
                report_id, title.strip(), content.strip(), severity.lower().strip()
            )

        self.save_run_data()
        return report_id

    def set_final_scan_result(
        self,
        content: str,
        success: bool = True,
    ) -> None:
        self.final_scan_result = content.strip()

        self.scan_results = {
            "scan_completed": True,
            "content": content,
            "success": success,
        }

        logger.info(f"Set final scan result: success={success}")
        self.save_run_data(mark_complete=True)

    def log_agent_creation(
        self, agent_id: str, name: str, task: str, parent_id: str | None = None
    ) -> None:
        agent_data: dict[str, Any] = {
            "id": agent_id,
            "name": name,
            "task": task,
            "status": "running",
            "parent_id": parent_id,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            "tool_executions": [],
        }

        self.agents[agent_id] = agent_data

    def log_chat_message(
        self,
        content: str,
        role: str,
        agent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        message_id = self._next_message_id
        self._next_message_id += 1

        message_data = {
            "message_id": message_id,
            "content": content,
            "role": role,
            "agent_id": agent_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "metadata": metadata or {},
        }

        self.chat_messages.append(message_data)
        return message_id

    def log_tool_execution_start(self, agent_id: str, tool_name: str, args: dict[str, Any]) -> int:
        execution_id = self._next_execution_id
        self._next_execution_id += 1

        now = datetime.now(UTC).isoformat()
        execution_data = {
            "execution_id": execution_id,
            "agent_id": agent_id,
            "tool_name": tool_name,
            "args": args,
            "status": "running",
            "result": None,
            "timestamp": now,
            "started_at": now,
            "completed_at": None,
        }

        self.tool_executions[execution_id] = execution_data

        if agent_id in self.agents:
            self.agents[agent_id]["tool_executions"].append(execution_id)

        return execution_id

    def update_tool_execution(
        self, execution_id: int, status: str, result: Any | None = None
    ) -> None:
        if execution_id in self.tool_executions:
            self.tool_executions[execution_id]["status"] = status
            self.tool_executions[execution_id]["result"] = result
            self.tool_executions[execution_id]["completed_at"] = datetime.now(UTC).isoformat()

    def update_agent_status(
        self, agent_id: str, status: str, error_message: str | None = None
    ) -> None:
        if agent_id in self.agents:
            self.agents[agent_id]["status"] = status
            self.agents[agent_id]["updated_at"] = datetime.now(UTC).isoformat()
            if error_message:
                self.agents[agent_id]["error_message"] = error_message

    def set_scan_config(self, config: dict[str, Any]) -> None:
        self.scan_config = config
        self.run_metadata.update(
            {
                "targets": config.get("targets", []),
                "user_instructions": config.get("user_instructions", ""),
                "max_iterations": config.get("max_iterations", 200),
            }
        )
        self.get_run_dir()

    def save_run_data(self, mark_complete: bool = False) -> None:
        try:
            run_dir = self.get_run_dir()
            if mark_complete:
                self.end_time = datetime.now(UTC).isoformat()

            if self.final_scan_result:
                penetration_test_report_file = run_dir / "penetration_test_report.md"
                with penetration_test_report_file.open("w", encoding="utf-8") as f:
                    f.write("# Security Penetration Test Report\n\n")
                    f.write(
                        f"**Generated:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
                    )
                    f.write(f"{self.final_scan_result}\n")
                logger.info(
                    f"Saved final penetration test report to: {penetration_test_report_file}"
                )

            if self.vulnerability_reports:
                vuln_dir = run_dir / "vulnerabilities"
                vuln_dir.mkdir(exist_ok=True)

                new_reports = [
                    report
                    for report in self.vulnerability_reports
                    if report["id"] not in self._saved_vuln_ids
                ]

                for report in new_reports:
                    vuln_file = vuln_dir / f"{report['id']}.md"
                    with vuln_file.open("w", encoding="utf-8") as f:
                        f.write(f"# {report['title']}\n\n")
                        f.write(f"**ID:** {report['id']}\n")
                        f.write(f"**Severity:** {report['severity'].upper()}\n")
                        f.write(f"**Found:** {report['timestamp']}\n\n")
                        f.write("## Description\n\n")
                        f.write(f"{report['content']}\n")
                    self._saved_vuln_ids.add(report["id"])

                if self.vulnerability_reports:
                    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
                    sorted_reports = sorted(
                        self.vulnerability_reports,
                        key=lambda x: (severity_order.get(x["severity"], 5), x["timestamp"]),
                    )

                    vuln_csv_file = run_dir / "vulnerabilities.csv"
                    with vuln_csv_file.open("w", encoding="utf-8", newline="") as f:
                        import csv

                        fieldnames = ["id", "title", "severity", "timestamp", "file"]
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()

                        for report in sorted_reports:
                            writer.writerow(
                                {
                                    "id": report["id"],
                                    "title": report["title"],
                                    "severity": report["severity"].upper(),
                                    "timestamp": report["timestamp"],
                                    "file": f"vulnerabilities/{report['id']}.md",
                                }
                            )

                if new_reports:
                    logger.info(
                        f"Saved {len(new_reports)} new vulnerability report(s) to: {vuln_dir}"
                    )
                logger.info(f"Updated vulnerability index: {vuln_csv_file}")

            logger.info(f"📊 Essential scan data saved to: {run_dir}")

        except (OSError, RuntimeError):
            logger.exception("Failed to save scan data")

    def _calculate_duration(self) -> float:
        try:
            start = datetime.fromisoformat(self.start_time.replace("Z", "+00:00"))
            if self.end_time:
                end = datetime.fromisoformat(self.end_time.replace("Z", "+00:00"))
                return (end - start).total_seconds()
        except (ValueError, TypeError):
            pass
        return 0.0

    def get_agent_tools(self, agent_id: str) -> list[dict[str, Any]]:
        return [
            exec_data
            for exec_data in self.tool_executions.values()
            if exec_data.get("agent_id") == agent_id
        ]

    def get_real_tool_count(self) -> int:
        return sum(
            1
            for exec_data in self.tool_executions.values()
            if exec_data.get("tool_name") not in ["scan_start_info", "subagent_start_info"]
        )

    def get_total_llm_stats(self) -> dict[str, Any]:
        from strix.tools.agents_graph.agents_graph_actions import _agent_instances

        total_stats = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_tokens": 0,
            "cache_creation_tokens": 0,
            "cost": 0.0,
            "requests": 0,
            "failed_requests": 0,
        }

        for agent_instance in _agent_instances.values():
            if hasattr(agent_instance, "llm") and hasattr(agent_instance.llm, "_total_stats"):
                agent_stats = agent_instance.llm._total_stats
                total_stats["input_tokens"] += agent_stats.input_tokens
                total_stats["output_tokens"] += agent_stats.output_tokens
                total_stats["cached_tokens"] += agent_stats.cached_tokens
                total_stats["cache_creation_tokens"] += agent_stats.cache_creation_tokens
                total_stats["cost"] += agent_stats.cost
                total_stats["requests"] += agent_stats.requests
                total_stats["failed_requests"] += agent_stats.failed_requests

        total_stats["cost"] = round(total_stats["cost"], 4)

        return {
            "total": total_stats,
            "total_tokens": total_stats["input_tokens"] + total_stats["output_tokens"],
        }

    def cleanup(self) -> None:
        self.save_run_data(mark_complete=True)
