import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional
from uuid import uuid4

from .run_plan import RunPlan


if TYPE_CHECKING:
    from collections.abc import Callable


logger = logging.getLogger(__name__)

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
        self._next_llm_response_id = 1
        self._saved_vuln_ids: set[str] = set()

        self.vulnerability_found_callback: Callable[[str, str, str, str], None] | None = None

        self._plan: RunPlan | None = None
        self._is_continuation: bool = False
        self._continuation_context: dict[str, Any] = {}

    @property
    def plan(self) -> RunPlan:
        """Get or create the run plan."""
        if self._plan is None:
            self._plan = RunPlan(run_name=self.run_name or self.run_id)
        return self._plan

    @plan.setter
    def plan(self, value: RunPlan) -> None:
        """Set the run plan."""
        self._plan = value

    def set_plan(self, plan: RunPlan) -> None:
        """Set the run plan (for loading from disk)."""
        self._plan = plan
        self._plan.run_name = self.run_name or self.run_id

    def save_plan(self) -> Path | None:
        """Save the current plan to the run directory."""
        if self._plan is None:
            return None

        run_dir = self.get_run_dir()
        return self._plan.save(run_dir)

    def load_plan(self) -> RunPlan | None:
        """Load the plan from the run directory if it exists."""
        run_dir = self.get_run_dir()
        plan = RunPlan.load(run_dir)
        if plan:
            self._plan = plan
            self._plan.run_name = self.run_name or self.run_id
        return plan

    def mark_as_continuation(self, context: dict[str, Any] | None = None) -> None:
        """Mark this run as a continuation of a previous run."""
        self._is_continuation = True
        self._continuation_context = context or {}
        self.run_metadata["is_continuation"] = True
        self.run_metadata["continuation_context"] = self._continuation_context

    @property
    def is_continuation(self) -> bool:
        """Check if this is a continuation run."""
        return self._is_continuation

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

    def log_llm_response(
        self,
        agent_id: str,
        agent_name: str,
        content: str,
        model: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_tokens: int = 0,
        cost: float = 0.0,
        tool_invocations: list[dict[str, Any]] | None = None,
        iteration: int = 0,
        error: str | None = None,
    ) -> int:
        """Log an LLM response to a JSON file in the run directory.

        Each response is stored as a separate file for efficient storage and
        retrieval. JSON format is used for structured data that can be easily
        parsed for reconciliation.
        """
        response_id = self._next_llm_response_id
        self._next_llm_response_id += 1

        timestamp = datetime.now(UTC)
        timestamp_str = timestamp.isoformat()
        timestamp_file = timestamp.strftime("%Y%m%d_%H%M%S")

        response_data = {
            "response_id": response_id,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "iteration": iteration,
            "timestamp": timestamp_str,
            "model": model,
            "content": content,
            "tool_invocations": tool_invocations,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cached_tokens": cached_tokens,
                "cost": round(cost, 6),
            },
            "error": error,
        }

        try:
            run_dir = self.get_run_dir()
            responses_dir = run_dir / "llm_responses"
            responses_dir.mkdir(exist_ok=True)

            filename = f"{response_id:05d}_{timestamp_file}_{agent_name}.json"
            response_file = responses_dir / filename

            with response_file.open("w", encoding="utf-8") as f:
                json.dump(response_data, f, indent=2, ensure_ascii=False)

            logger.debug(f"Saved LLM response {response_id} to: {response_file}")

        except (OSError, RuntimeError) as e:
            logger.warning(f"Failed to save LLM response {response_id}: {e}")

        return response_id

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

            if self._plan is not None:
                self._plan.save(run_dir)

            self._save_run_state(run_dir, mark_complete)

            logger.info(f"📊 Essential scan data saved to: {run_dir}")

        except (OSError, RuntimeError):
            logger.exception("Failed to save scan data")

    def _save_run_state(self, run_dir: Path, mark_complete: bool = False) -> None:
        """Save the run state for continuation."""
        state_file = run_dir / "run_state.json"

        run_state = {
            "run_id": self.run_id,
            "run_name": self.run_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "is_complete": mark_complete,
            "is_continuation": self._is_continuation,
            "continuation_context": self._continuation_context,
            "scan_config": self.scan_config,
            "run_metadata": self.run_metadata,
            "agents_count": len(self.agents),
            "tool_executions_count": len(self.tool_executions),
            "chat_messages_count": len(self.chat_messages),
            "vulnerability_reports_count": len(self.vulnerability_reports),
            "has_plan": self._plan is not None,
            "plan_progress": self._plan.get_progress() if self._plan else None,
        }

        with state_file.open("w", encoding="utf-8") as f:
            json.dump(run_state, f, indent=2, ensure_ascii=False)

    @classmethod
    def load_run_state(cls, run_dir: Path) -> dict[str, Any] | None:
        """Load run state from a directory."""
        state_file = run_dir / "run_state.json"

        if not state_file.exists():
            return None

        try:
            with state_file.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load run state: {e}")
            return None

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
