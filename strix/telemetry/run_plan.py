"""Run plan module for tracking sequential tasks and enabling run continuation.

This module provides:
1. RunPlan - A sequential task list that can be persisted and resumed
2. PlanTask - Individual tasks with status tracking
3. PlanPhase - Grouping of related tasks into phases
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4


logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Status of a task in the run plan."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class PhaseStatus(str, Enum):
    """Status of a phase in the run plan."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"


@dataclass
class PlanTask:
    """A single task in the run plan."""

    task_id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    phase_id: str | None = None
    depends_on: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    started_at: str | None = None
    completed_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    iteration_started: int | None = None
    iteration_completed: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "phase_id": self.phase_id,
            "depends_on": self.depends_on,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
            "iteration_started": self.iteration_started,
            "iteration_completed": self.iteration_completed,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlanTask":
        return cls(
            task_id=data["task_id"],
            title=data["title"],
            description=data.get("description", ""),
            status=TaskStatus(data.get("status", "pending")),
            phase_id=data.get("phase_id"),
            depends_on=data.get("depends_on", []),
            created_at=data.get("created_at", datetime.now(UTC).isoformat()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            result=data.get("result"),
            error=data.get("error"),
            iteration_started=data.get("iteration_started"),
            iteration_completed=data.get("iteration_completed"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class PlanPhase:
    """A phase grouping multiple related tasks."""

    phase_id: str
    title: str
    description: str = ""
    order: int = 0
    status: PhaseStatus = PhaseStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    started_at: str | None = None
    completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase_id": self.phase_id,
            "title": self.title,
            "description": self.description,
            "order": self.order,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlanPhase":
        return cls(
            phase_id=data["phase_id"],
            title=data["title"],
            description=data.get("description", ""),
            order=data.get("order", 0),
            status=PhaseStatus(data.get("status", "pending")),
            created_at=data.get("created_at", datetime.now(UTC).isoformat()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
        )


@dataclass
class RunPlan:
    """A sequential plan of tasks for a run that can be persisted and resumed."""

    plan_id: str = field(default_factory=lambda: f"plan_{uuid4().hex[:8]}")
    run_name: str = ""
    title: str = "Run Plan"
    description: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    phases: list[PlanPhase] = field(default_factory=list)
    tasks: list[PlanTask] = field(default_factory=list)
    current_task_id: str | None = None
    current_phase_id: str | None = None
    is_paused: bool = False
    pause_reason: str | None = None
    resume_context: dict[str, Any] = field(default_factory=dict)

    def add_phase(
        self,
        title: str,
        description: str = "",
        phase_id: str | None = None,
    ) -> PlanPhase:
        """Add a new phase to the plan."""
        phase = PlanPhase(
            phase_id=phase_id or f"phase_{len(self.phases) + 1}",
            title=title,
            description=description,
            order=len(self.phases),
        )
        self.phases.append(phase)
        self._update_timestamp()
        return phase

    def add_task(
        self,
        title: str,
        description: str = "",
        phase_id: str | None = None,
        depends_on: list[str] | None = None,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PlanTask:
        """Add a new task to the plan."""
        task = PlanTask(
            task_id=task_id or f"task_{len(self.tasks) + 1}",
            title=title,
            description=description,
            phase_id=phase_id,
            depends_on=depends_on or [],
            metadata=metadata or {},
        )
        self.tasks.append(task)
        self._update_timestamp()
        return task

    def start_task(self, task_id: str, iteration: int | None = None) -> PlanTask | None:
        """Mark a task as in progress."""
        task = self.get_task(task_id)
        if task:
            task.status = TaskStatus.IN_PROGRESS
            task.started_at = datetime.now(UTC).isoformat()
            task.iteration_started = iteration
            self.current_task_id = task_id

            if task.phase_id:
                phase = self.get_phase(task.phase_id)
                if phase and phase.status == PhaseStatus.PENDING:
                    phase.status = PhaseStatus.IN_PROGRESS
                    phase.started_at = datetime.now(UTC).isoformat()
                    self.current_phase_id = phase.phase_id

            self._update_timestamp()
            logger.info(f"Started task: {task.title}")
        return task

    def complete_task(
        self,
        task_id: str,
        result: dict[str, Any] | None = None,
        iteration: int | None = None,
    ) -> PlanTask | None:
        """Mark a task as completed."""
        task = self.get_task(task_id)
        if task:
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now(UTC).isoformat()
            task.result = result
            task.iteration_completed = iteration

            if self.current_task_id == task_id:
                self.current_task_id = None

            self._update_phase_status(task.phase_id)
            self._update_timestamp()
            logger.info(f"Completed task: {task.title}")
        return task

    def fail_task(
        self,
        task_id: str,
        error: str,
        iteration: int | None = None,
    ) -> PlanTask | None:
        """Mark a task as failed."""
        task = self.get_task(task_id)
        if task:
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.now(UTC).isoformat()
            task.error = error
            task.iteration_completed = iteration

            if self.current_task_id == task_id:
                self.current_task_id = None

            self._update_phase_status(task.phase_id)
            self._update_timestamp()
            logger.warning(f"Failed task: {task.title} - {error}")
        return task

    def skip_task(self, task_id: str, reason: str = "") -> PlanTask | None:
        """Skip a task."""
        task = self.get_task(task_id)
        if task:
            task.status = TaskStatus.SKIPPED
            task.completed_at = datetime.now(UTC).isoformat()
            task.error = reason or "Skipped"
            self._update_phase_status(task.phase_id)
            self._update_timestamp()
            logger.info(f"Skipped task: {task.title}")
        return task

    def get_task(self, task_id: str) -> PlanTask | None:
        """Get a task by ID."""
        for task in self.tasks:
            if task.task_id == task_id:
                return task
        return None

    def get_phase(self, phase_id: str) -> PlanPhase | None:
        """Get a phase by ID."""
        for phase in self.phases:
            if phase.phase_id == phase_id:
                return phase
        return None

    def get_next_task(self) -> PlanTask | None:
        """Get the next pending task that has all dependencies satisfied."""
        completed_ids = {t.task_id for t in self.tasks if t.status == TaskStatus.COMPLETED}

        for task in self.tasks:
            if task.status != TaskStatus.PENDING:
                continue

            deps_satisfied = all(dep in completed_ids for dep in task.depends_on)
            if deps_satisfied:
                return task

        return None

    def get_current_task(self) -> PlanTask | None:
        """Get the currently in-progress task."""
        if self.current_task_id:
            return self.get_task(self.current_task_id)

        for task in self.tasks:
            if task.status == TaskStatus.IN_PROGRESS:
                return task

        return None

    def get_tasks_by_phase(self, phase_id: str) -> list[PlanTask]:
        """Get all tasks for a specific phase."""
        return [t for t in self.tasks if t.phase_id == phase_id]

    def get_pending_tasks(self) -> list[PlanTask]:
        """Get all pending tasks."""
        return [t for t in self.tasks if t.status == TaskStatus.PENDING]

    def get_completed_tasks(self) -> list[PlanTask]:
        """Get all completed tasks."""
        return [t for t in self.tasks if t.status == TaskStatus.COMPLETED]

    def get_failed_tasks(self) -> list[PlanTask]:
        """Get all failed tasks."""
        return [t for t in self.tasks if t.status == TaskStatus.FAILED]

    def is_complete(self) -> bool:
        """Check if all tasks are completed or skipped."""
        return all(
            t.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED, TaskStatus.FAILED)
            for t in self.tasks
        )

    def get_progress(self) -> dict[str, Any]:
        """Get plan progress summary."""
        total = len(self.tasks)
        completed = sum(1 for t in self.tasks if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in self.tasks if t.status == TaskStatus.FAILED)
        skipped = sum(1 for t in self.tasks if t.status == TaskStatus.SKIPPED)
        in_progress = sum(1 for t in self.tasks if t.status == TaskStatus.IN_PROGRESS)
        pending = sum(1 for t in self.tasks if t.status == TaskStatus.PENDING)

        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "skipped": skipped,
            "in_progress": in_progress,
            "pending": pending,
            "percent_complete": round((completed / max(1, total)) * 100, 1),
            "is_complete": self.is_complete(),
        }

    def pause(self, reason: str = "", context: dict[str, Any] | None = None) -> None:
        """Pause the plan execution."""
        self.is_paused = True
        self.pause_reason = reason
        if context:
            self.resume_context = context
        self._update_timestamp()
        logger.info(f"Plan paused: {reason}")

    def resume(self) -> dict[str, Any]:
        """Resume the plan execution."""
        context = self.resume_context.copy()
        self.is_paused = False
        self.pause_reason = None
        self.resume_context = {}
        self._update_timestamp()
        logger.info("Plan resumed")
        return context

    def _update_phase_status(self, phase_id: str | None) -> None:
        """Update phase status based on its tasks."""
        if not phase_id:
            return

        phase = self.get_phase(phase_id)
        if not phase:
            return

        tasks = self.get_tasks_by_phase(phase_id)
        if not tasks:
            return

        all_completed = all(t.status == TaskStatus.COMPLETED for t in tasks)
        any_failed = any(t.status == TaskStatus.FAILED for t in tasks)
        any_in_progress = any(t.status == TaskStatus.IN_PROGRESS for t in tasks)
        all_done = all(
            t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.SKIPPED)
            for t in tasks
        )

        if all_completed:
            phase.status = PhaseStatus.COMPLETED
            phase.completed_at = datetime.now(UTC).isoformat()
        elif any_failed and all_done:
            phase.status = PhaseStatus.PARTIALLY_COMPLETED
            phase.completed_at = datetime.now(UTC).isoformat()
        elif any_in_progress:
            phase.status = PhaseStatus.IN_PROGRESS

    def _update_timestamp(self) -> None:
        """Update the last modified timestamp."""
        self.updated_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Convert plan to dictionary for serialization."""
        return {
            "plan_id": self.plan_id,
            "run_name": self.run_name,
            "title": self.title,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "phases": [p.to_dict() for p in self.phases],
            "tasks": [t.to_dict() for t in self.tasks],
            "current_task_id": self.current_task_id,
            "current_phase_id": self.current_phase_id,
            "is_paused": self.is_paused,
            "pause_reason": self.pause_reason,
            "resume_context": self.resume_context,
            "progress": self.get_progress(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunPlan":
        """Create a plan from a dictionary."""
        plan = cls(
            plan_id=data.get("plan_id", f"plan_{uuid4().hex[:8]}"),
            run_name=data.get("run_name", ""),
            title=data.get("title", "Run Plan"),
            description=data.get("description", ""),
            created_at=data.get("created_at", datetime.now(UTC).isoformat()),
            updated_at=data.get("updated_at", datetime.now(UTC).isoformat()),
            current_task_id=data.get("current_task_id"),
            current_phase_id=data.get("current_phase_id"),
            is_paused=data.get("is_paused", False),
            pause_reason=data.get("pause_reason"),
            resume_context=data.get("resume_context", {}),
        )

        for phase_data in data.get("phases", []):
            plan.phases.append(PlanPhase.from_dict(phase_data))

        for task_data in data.get("tasks", []):
            plan.tasks.append(PlanTask.from_dict(task_data))

        return plan

    def save(self, run_dir: Path) -> Path:
        """Save the plan to a JSON file in the run directory."""
        plan_file = run_dir / "run_plan.json"

        with plan_file.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

        logger.debug(f"Saved run plan to: {plan_file}")
        return plan_file

    @classmethod
    def load(cls, run_dir: Path) -> "RunPlan | None":
        """Load a plan from a run directory."""
        plan_file = run_dir / "run_plan.json"

        if not plan_file.exists():
            return None

        try:
            with plan_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info(f"Loaded run plan from: {plan_file}")
            return cls.from_dict(data)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load run plan: {e}")
            return None

    def get_summary_text(self) -> str:
        """Get a human-readable summary of the plan."""
        lines = [
            "=" * 60,
            f"RUN PLAN: {self.title}",
            "=" * 60,
            f"Plan ID: {self.plan_id}",
            f"Run Name: {self.run_name}",
            f"Created: {self.created_at}",
            f"Updated: {self.updated_at}",
            "",
        ]

        progress = self.get_progress()
        lines.extend(
            [
                "--- PROGRESS ---",
                f"Total Tasks: {progress['total']}",
                f"Completed: {progress['completed']} ({progress['percent_complete']}%)",
                f"In Progress: {progress['in_progress']}",
                f"Pending: {progress['pending']}",
                f"Failed: {progress['failed']}",
                f"Skipped: {progress['skipped']}",
                "",
            ]
        )

        if self.is_paused:
            lines.extend(
                [
                    "--- PAUSED ---",
                    f"Reason: {self.pause_reason or 'No reason given'}",
                    "",
                ]
            )

        if self.phases:
            lines.append("--- PHASES ---")
            for phase in sorted(self.phases, key=lambda p: p.order):
                status_icon = {
                    PhaseStatus.PENDING: "○",
                    PhaseStatus.IN_PROGRESS: "◐",
                    PhaseStatus.COMPLETED: "●",
                    PhaseStatus.PARTIALLY_COMPLETED: "◑",
                    PhaseStatus.FAILED: "✗",
                }.get(phase.status, "?")
                lines.append(f"  {status_icon} {phase.title} [{phase.status.value}]")
            lines.append("")

        lines.append("--- TASKS ---")
        for task in self.tasks:
            status_icon = {
                TaskStatus.PENDING: "○",
                TaskStatus.IN_PROGRESS: "◐",
                TaskStatus.COMPLETED: "●",
                TaskStatus.FAILED: "✗",
                TaskStatus.SKIPPED: "⊘",
                TaskStatus.BLOCKED: "⊗",
            }.get(task.status, "?")
            phase_info = f" [{task.phase_id}]" if task.phase_id else ""
            lines.append(f"  {status_icon} {task.title}{phase_info} - {task.status.value}")

        lines.append("=" * 60)
        return "\n".join(lines)
