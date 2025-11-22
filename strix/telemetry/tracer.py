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


class EventType(Enum):
    """Types of events tracked by the tracer."""

    # Agent lifecycle events
    AGENT_CREATED = "agent_created"
    AGENT_STATUS_CHANGED = "agent_status_changed"
    AGENT_ITERATION = "agent_iteration"
    AGENT_STATE_TRANSITION = "agent_state_transition"

    # Tool events
    TOOL_START = "tool_start"
    TOOL_COMPLETE = "tool_complete"
    TOOL_ERROR = "tool_error"

    # LLM events
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    LLM_ERROR = "llm_error"

    # Inter-agent communication
    AGENT_MESSAGE_SENT = "agent_message_sent"
    AGENT_MESSAGE_RECEIVED = "agent_message_received"

    # Vulnerability events
    VULNERABILITY_FOUND = "vulnerability_found"

    # Scan events
    SCAN_START = "scan_start"
    SCAN_COMPLETE = "scan_complete"


@dataclass
class TracerEvent:
    """A single event in the tracer event stream."""

    event_type: EventType
    timestamp: str
    agent_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "agent_id": self.agent_id,
            "data": self.data,
        }

_global_tracer: Optional["Tracer"] = None


def get_global_tracer() -> Optional["Tracer"]:
    return _global_tracer


def set_global_tracer(tracer: "Tracer") -> None:
    global _global_tracer  # noqa: PLW0603
    _global_tracer = tracer


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

        # Unified event stream for real-time visibility
        self.events: list[TracerEvent] = []
        self._event_cursor: int = 0  # For consumers to track their position

        # Callbacks for real-time notifications
        self.vulnerability_found_callback: Callable[[str, str, str, str], None] | None = None
        self.event_callback: Callable[[TracerEvent], None] | None = None

    def set_run_name(self, run_name: str) -> None:
        self.run_name = run_name
        self.run_id = run_name

    def get_run_dir(self) -> Path:
        if self._run_dir is None:
            runs_dir = Path.cwd() / "agent_runs"
            runs_dir.mkdir(exist_ok=True)

            run_dir_name = self.run_name if self.run_name else self.run_id
            self._run_dir = runs_dir / run_dir_name
            self._run_dir.mkdir(exist_ok=True)

        return self._run_dir

    def _save_metadata(self) -> None:
        """Save metadata.json to run directory (called on scan start and updates)."""
        try:
            metadata_file = self.get_run_dir() / "metadata.json"
            # Use atomic write pattern
            temp_file = metadata_file.with_suffix(".json.tmp")
            with temp_file.open("w", encoding="utf-8") as f:
                json.dump(self.run_metadata, f, indent=2, ensure_ascii=False, default=str)
            temp_file.replace(metadata_file)
            logger.debug(f"Metadata saved to {metadata_file}")
        except (OSError, IOError) as e:
            logger.warning(f"Failed to save metadata: {e}")

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

        # Immediately persist metadata on scan start
        self._save_metadata()

        # Emit scan start event
        event = TracerEvent(
            event_type=EventType.SCAN_START,
            timestamp=datetime.now(UTC).isoformat(),
            agent_id=None,
            data={
                "run_id": self.run_id,
                "run_name": self.run_name,
                "targets": config.get("targets", []),
                "max_iterations": config.get("max_iterations", 200),
            },
        )
        self._emit_event(event)

    def save_run_data(self) -> None:
        try:
            run_dir = self.get_run_dir()
            self.end_time = datetime.now(UTC).isoformat()

            # Update and persist final metadata
            self.run_metadata["end_time"] = self.end_time
            self.run_metadata["status"] = "completed"
            self.run_metadata["vulnerability_count"] = len(self.vulnerability_reports)
            self.run_metadata["duration_seconds"] = self._calculate_duration()
            self._save_metadata()

            # Emit scan complete event
            event = TracerEvent(
                event_type=EventType.SCAN_COMPLETE,
                timestamp=self.end_time,
                agent_id=None,
                data={
                    "run_id": self.run_id,
                    "duration_seconds": self._calculate_duration(),
                    "vulnerability_count": len(self.vulnerability_reports),
                    "agent_count": len(self.agents),
                    "tool_execution_count": len(self.tool_executions),
                },
            )
            self._emit_event(event)

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

                severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
                sorted_reports = sorted(
                    self.vulnerability_reports,
                    key=lambda x: (severity_order.get(x["severity"], 5), x["timestamp"]),
                )

                for report in sorted_reports:
                    vuln_file = vuln_dir / f"{report['id']}.md"
                    with vuln_file.open("w", encoding="utf-8") as f:
                        f.write(f"# {report['title']}\n\n")
                        f.write(f"**ID:** {report['id']}\n")
                        f.write(f"**Severity:** {report['severity'].upper()}\n")
                        f.write(f"**Found:** {report['timestamp']}\n\n")
                        f.write("## Description\n\n")
                        f.write(f"{report['content']}\n")

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

                logger.info(
                    f"Saved {len(self.vulnerability_reports)} vulnerability reports to: {vuln_dir}"
                )
                logger.info(f"Saved vulnerability index to: {vuln_csv_file}")

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
        self.save_run_data()

    # =========================================================================
    # New Event Stream Methods for Real-Time Visibility
    # =========================================================================

    def _emit_event(self, event: TracerEvent) -> None:
        """Add event to stream, persist to JSONL, and notify callback if registered."""
        self.events.append(event)

        # Append to JSONL file (crash-safe, append-only)
        try:
            events_file = self.get_run_dir() / "events.jsonl"
            with events_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict(), default=str) + "\n")
        except (OSError, IOError) as e:
            logger.warning(f"Failed to append event to JSONL: {e}")

        if self.event_callback:
            try:
                self.event_callback(event)
            except Exception:  # noqa: BLE001
                logger.exception("Error in event callback")

    def log_agent_iteration(
        self,
        agent_id: str,
        iteration: int,
        max_iterations: int,
    ) -> None:
        """Log an agent iteration event."""
        event = TracerEvent(
            event_type=EventType.AGENT_ITERATION,
            timestamp=datetime.now(UTC).isoformat(),
            agent_id=agent_id,
            data={
                "iteration": iteration,
                "max_iterations": max_iterations,
                "progress_pct": round((iteration / max_iterations) * 100, 1),
            },
        )
        self._emit_event(event)

    def log_agent_state_transition(
        self,
        agent_id: str,
        from_state: str,
        to_state: str,
        reason: str | None = None,
    ) -> None:
        """Log an agent state transition event."""
        event = TracerEvent(
            event_type=EventType.AGENT_STATE_TRANSITION,
            timestamp=datetime.now(UTC).isoformat(),
            agent_id=agent_id,
            data={
                "from_state": from_state,
                "to_state": to_state,
                "reason": reason,
            },
        )
        self._emit_event(event)

    def log_llm_request(
        self,
        agent_id: str,
        model: str,
        prompt_tokens: int | None = None,
        request_id: str | None = None,
    ) -> str:
        """Log an LLM request event. Returns request_id for correlation."""
        if request_id is None:
            request_id = f"llm-{self._next_event_id}"
            self._next_event_id += 1

        event = TracerEvent(
            event_type=EventType.LLM_REQUEST,
            timestamp=datetime.now(UTC).isoformat(),
            agent_id=agent_id,
            data={
                "request_id": request_id,
                "model": model,
                "prompt_tokens": prompt_tokens,
            },
        )
        self._emit_event(event)
        return request_id

    def log_llm_response(
        self,
        agent_id: str,
        request_id: str,
        input_tokens: int,
        output_tokens: int,
        duration_ms: float,
        cost: float | None = None,
        cached_tokens: int = 0,
    ) -> None:
        """Log an LLM response event."""
        event = TracerEvent(
            event_type=EventType.LLM_RESPONSE,
            timestamp=datetime.now(UTC).isoformat(),
            agent_id=agent_id,
            data={
                "request_id": request_id,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cached_tokens": cached_tokens,
                "total_tokens": input_tokens + output_tokens,
                "duration_ms": round(duration_ms, 1),
                "cost": round(cost, 6) if cost else None,
            },
        )
        self._emit_event(event)

    def log_llm_error(
        self,
        agent_id: str,
        request_id: str,
        error: str,
        duration_ms: float | None = None,
    ) -> None:
        """Log an LLM error event."""
        event = TracerEvent(
            event_type=EventType.LLM_ERROR,
            timestamp=datetime.now(UTC).isoformat(),
            agent_id=agent_id,
            data={
                "request_id": request_id,
                "error": error,
                "duration_ms": round(duration_ms, 1) if duration_ms else None,
            },
        )
        self._emit_event(event)

    def log_agent_message_sent(
        self,
        from_agent_id: str,
        to_agent_id: str,
        message: str,
    ) -> None:
        """Log an inter-agent message sent event."""
        event = TracerEvent(
            event_type=EventType.AGENT_MESSAGE_SENT,
            timestamp=datetime.now(UTC).isoformat(),
            agent_id=from_agent_id,
            data={
                "to_agent_id": to_agent_id,
                "message_preview": message[:200] + "..." if len(message) > 200 else message,
                "message_length": len(message),
            },
        )
        self._emit_event(event)

    def log_agent_message_received(
        self,
        agent_id: str,
        from_agent_id: str,
        message: str,
    ) -> None:
        """Log an inter-agent message received event."""
        event = TracerEvent(
            event_type=EventType.AGENT_MESSAGE_RECEIVED,
            timestamp=datetime.now(UTC).isoformat(),
            agent_id=agent_id,
            data={
                "from_agent_id": from_agent_id,
                "message_preview": message[:200] + "..." if len(message) > 200 else message,
                "message_length": len(message),
            },
        )
        self._emit_event(event)

    def log_tool_event(
        self,
        agent_id: str,
        tool_name: str,
        event_type: EventType,
        args: dict[str, Any] | None = None,
        result: Any | None = None,
        error: str | None = None,
        duration_ms: float | None = None,
    ) -> None:
        """Log a tool execution event (start, complete, or error)."""
        data: dict[str, Any] = {"tool_name": tool_name}

        if args is not None:
            # Truncate large args for display
            args_str = str(args)
            if len(args_str) > 500:
                data["args_preview"] = args_str[:500] + "..."
            else:
                data["args"] = args

        if result is not None:
            result_str = str(result)
            if len(result_str) > 500:
                data["result_preview"] = result_str[:500] + "..."
            else:
                data["result"] = result

        if error is not None:
            data["error"] = error

        if duration_ms is not None:
            data["duration_ms"] = round(duration_ms, 1)

        event = TracerEvent(
            event_type=event_type,
            timestamp=datetime.now(UTC).isoformat(),
            agent_id=agent_id,
            data=data,
        )
        self._emit_event(event)

    def get_events_since(self, cursor: int = 0) -> tuple[list[TracerEvent], int]:
        """Get all events since the given cursor position.

        Returns (events, new_cursor) tuple.
        """
        new_events = self.events[cursor:]
        return new_events, len(self.events)

    def get_recent_events(self, count: int = 50) -> list[TracerEvent]:
        """Get the most recent N events."""
        return self.events[-count:] if self.events else []
