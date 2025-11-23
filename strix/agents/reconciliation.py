"""State reconciliation module for identifying and patching errors in agent state.

This module provides functionality to:
1. Serialize complete agent state for analysis
2. Identify inconsistencies and errors in state
3. Generate and apply patches to fix issues
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from strix.agents.state import AgentState


logger = logging.getLogger(__name__)


class ReconciliationIssueType(str, Enum):
    """Types of issues that can be identified during reconciliation."""

    STATE_INCONSISTENCY = "state_inconsistency"
    MISSING_DATA = "missing_data"
    DUPLICATE_DATA = "duplicate_data"
    INVALID_VALUE = "invalid_value"
    STALE_DATA = "stale_data"
    LOOP_DETECTED = "loop_detected"
    RATE_LIMIT_DETECTED = "rate_limit_detected"


@dataclass
class ReconciliationIssue:
    """Represents an issue found during reconciliation."""

    issue_type: ReconciliationIssueType
    description: str
    field_path: str
    current_value: Any = None
    suggested_value: Any = None
    severity: str = "medium"  # low, medium, high, critical
    auto_fixable: bool = False


@dataclass
class ReconciliationPatch:
    """A patch to apply to the agent state."""

    field_path: str
    operation: str  # set, append, remove, clear
    value: Any = None
    reason: str = ""


@dataclass
class ReconciliationResult:
    """Result of a reconciliation check."""

    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    issues: list[ReconciliationIssue] = field(default_factory=list)
    patches_applied: list[ReconciliationPatch] = field(default_factory=list)
    state_hash_before: str = ""
    state_hash_after: str = ""
    success: bool = True
    error_message: str | None = None


class StateReconciler:
    """Handles state reconciliation for agents."""

    def __init__(self, state: "AgentState"):
        self.state = state
        self._reconciliation_history: list[ReconciliationResult] = []

    def get_complete_state_for_reconciliation(self) -> dict[str, Any]:
        """Get the complete agent state formatted for reconciliation analysis.

        Returns a structured representation of the state that can be sent to
        an LLM for analysis or stored for debugging.
        """
        state_dump = self.state.model_dump()

        recent_messages_count = min(10, len(self.state.messages))
        recent_messages = self.state.messages[-recent_messages_count:] if self.state.messages else []

        recent_actions_count = min(10, len(self.state.actions_taken))
        recent_actions = (
            self.state.actions_taken[-recent_actions_count:] if self.state.actions_taken else []
        )

        recent_errors_count = min(10, len(self.state.errors))
        recent_errors = self.state.errors[-recent_errors_count:] if self.state.errors else []

        reconciliation_state = {
            "meta": {
                "reconciliation_timestamp": datetime.now(UTC).isoformat(),
                "state_version": "1.0",
            },
            "identity": {
                "agent_id": state_dump.get("agent_id"),
                "agent_name": state_dump.get("agent_name"),
                "parent_id": state_dump.get("parent_id"),
            },
            "execution_status": {
                "task": state_dump.get("task"),
                "iteration": state_dump.get("iteration"),
                "max_iterations": state_dump.get("max_iterations"),
                "completed": state_dump.get("completed"),
                "stop_requested": state_dump.get("stop_requested"),
                "waiting_for_input": state_dump.get("waiting_for_input"),
                "llm_failed": state_dump.get("llm_failed"),
                "max_iterations_warning_sent": state_dump.get("max_iterations_warning_sent"),
            },
            "timing": {
                "start_time": state_dump.get("start_time"),
                "last_updated": state_dump.get("last_updated"),
                "waiting_start_time": str(state_dump.get("waiting_start_time"))
                if state_dump.get("waiting_start_time")
                else None,
            },
            "counts": {
                "total_messages": len(self.state.messages),
                "total_actions": len(self.state.actions_taken),
                "total_observations": len(self.state.observations),
                "total_errors": len(self.state.errors),
            },
            "recent_activity": {
                "recent_messages": recent_messages,
                "recent_actions": recent_actions,
                "recent_errors": recent_errors,
            },
            "context": state_dump.get("context", {}),
            "final_result": state_dump.get("final_result"),
        }

        return reconciliation_state

    def get_state_as_text(self) -> str:
        """Get the state as a formatted text block for LLM analysis."""
        state = self.get_complete_state_for_reconciliation()

        lines = [
            "=" * 60,
            "AGENT STATE RECONCILIATION REPORT",
            "=" * 60,
            "",
            f"Reconciliation Time: {state['meta']['reconciliation_timestamp']}",
            "",
            "--- IDENTITY ---",
            f"Agent ID: {state['identity']['agent_id']}",
            f"Agent Name: {state['identity']['agent_name']}",
            f"Parent ID: {state['identity']['parent_id'] or 'None (Root Agent)'}",
            "",
            "--- EXECUTION STATUS ---",
            f"Task: {state['execution_status']['task'][:200]}..."
            if len(state["execution_status"]["task"]) > 200
            else f"Task: {state['execution_status']['task']}",
            f"Iteration: {state['execution_status']['iteration']}/{state['execution_status']['max_iterations']}",
            f"Completed: {state['execution_status']['completed']}",
            f"Stop Requested: {state['execution_status']['stop_requested']}",
            f"Waiting for Input: {state['execution_status']['waiting_for_input']}",
            f"LLM Failed: {state['execution_status']['llm_failed']}",
            "",
            "--- COUNTS ---",
            f"Total Messages: {state['counts']['total_messages']}",
            f"Total Actions: {state['counts']['total_actions']}",
            f"Total Observations: {state['counts']['total_observations']}",
            f"Total Errors: {state['counts']['total_errors']}",
            "",
        ]

        if state["recent_activity"]["recent_errors"]:
            lines.extend(
                [
                    "--- RECENT ERRORS ---",
                ]
            )
            for err in state["recent_activity"]["recent_errors"]:
                lines.append(f"  - {err}")
            lines.append("")

        if state["recent_activity"]["recent_messages"]:
            lines.extend(
                [
                    "--- RECENT MESSAGES (last 10) ---",
                ]
            )
            for msg in state["recent_activity"]["recent_messages"]:
                role = msg.get("role", "unknown")
                content = str(msg.get("content", ""))[:200]
                lines.append(f"  [{role}]: {content}...")
            lines.append("")

        lines.extend(
            [
                "=" * 60,
            ]
        )

        return "\n".join(lines)

    def check_for_issues(self) -> list[ReconciliationIssue]:
        """Automatically check for common issues in the state."""
        issues: list[ReconciliationIssue] = []

        if self.state.llm_failed and not self.state.waiting_for_input:
            issues.append(
                ReconciliationIssue(
                    issue_type=ReconciliationIssueType.STATE_INCONSISTENCY,
                    description="LLM failed but agent not in waiting state",
                    field_path="llm_failed",
                    current_value=True,
                    suggested_value=False,
                    severity="high",
                    auto_fixable=True,
                )
            )

        if self.state.completed and not self.state.stop_requested:
            pass

        if self.state.iteration > self.state.max_iterations:
            issues.append(
                ReconciliationIssue(
                    issue_type=ReconciliationIssueType.INVALID_VALUE,
                    description="Iteration count exceeds max_iterations",
                    field_path="iteration",
                    current_value=self.state.iteration,
                    suggested_value=self.state.max_iterations,
                    severity="medium",
                    auto_fixable=True,
                )
            )

        rate_limit_errors = [
            e for e in self.state.errors if "rate limit" in e.lower() or "429" in e.lower()
        ]
        if len(rate_limit_errors) >= 3:
            issues.append(
                ReconciliationIssue(
                    issue_type=ReconciliationIssueType.RATE_LIMIT_DETECTED,
                    description=f"Multiple rate limit errors detected ({len(rate_limit_errors)} errors)",
                    field_path="errors",
                    current_value=len(rate_limit_errors),
                    severity="high",
                    auto_fixable=False,
                )
            )

        if len(self.state.messages) >= 6:
            last_messages = self.state.messages[-6:]
            assistant_messages = [m for m in last_messages if m.get("role") == "assistant"]
            if len(assistant_messages) >= 3:
                contents = [str(m.get("content", ""))[:100] for m in assistant_messages]
                if len(set(contents)) == 1:
                    issues.append(
                        ReconciliationIssue(
                            issue_type=ReconciliationIssueType.LOOP_DETECTED,
                            description="Agent appears to be in a loop (repeated identical responses)",
                            field_path="messages",
                            current_value=contents[0],
                            severity="critical",
                            auto_fixable=False,
                        )
                    )

        if self.state.waiting_for_input and self.state.waiting_start_time:
            elapsed = (datetime.now(UTC) - self.state.waiting_start_time).total_seconds()
            if elapsed > 300 and not self.state.llm_failed:
                issues.append(
                    ReconciliationIssue(
                        issue_type=ReconciliationIssueType.STALE_DATA,
                        description=f"Agent has been waiting for input for {elapsed:.0f} seconds",
                        field_path="waiting_for_input",
                        current_value=True,
                        severity="medium",
                        auto_fixable=False,
                    )
                )

        return issues

    def apply_patch(self, patch: ReconciliationPatch) -> bool:
        """Apply a single patch to the state.

        Returns True if the patch was applied successfully.
        """
        try:
            field_path = patch.field_path
            operation = patch.operation

            if operation == "set":
                if hasattr(self.state, field_path):
                    setattr(self.state, field_path, patch.value)
                    logger.info(f"Applied patch: set {field_path} = {patch.value}")
                    return True
                logger.warning(f"Cannot apply patch: field '{field_path}' not found")
                return False

            elif operation == "clear":
                if hasattr(self.state, field_path):
                    attr = getattr(self.state, field_path)
                    if isinstance(attr, list):
                        attr.clear()
                    elif isinstance(attr, dict):
                        attr.clear()
                    elif isinstance(attr, str):
                        setattr(self.state, field_path, "")
                    else:
                        setattr(self.state, field_path, None)
                    logger.info(f"Applied patch: cleared {field_path}")
                    return True
                return False

            elif operation == "append":
                if hasattr(self.state, field_path):
                    attr = getattr(self.state, field_path)
                    if isinstance(attr, list):
                        attr.append(patch.value)
                        logger.info(f"Applied patch: appended to {field_path}")
                        return True
                return False

            elif operation == "remove":
                if hasattr(self.state, field_path):
                    attr = getattr(self.state, field_path)
                    if isinstance(attr, list) and patch.value in attr:
                        attr.remove(patch.value)
                        logger.info(f"Applied patch: removed from {field_path}")
                        return True
                return False

            else:
                logger.warning(f"Unknown patch operation: {operation}")
                return False

        except Exception as e:
            logger.error(f"Failed to apply patch: {e}")
            return False

    def auto_fix_issues(self) -> ReconciliationResult:
        """Automatically fix all auto-fixable issues."""
        result = ReconciliationResult()
        result.issues = self.check_for_issues()

        for issue in result.issues:
            if issue.auto_fixable and issue.suggested_value is not None:
                patch = ReconciliationPatch(
                    field_path=issue.field_path,
                    operation="set",
                    value=issue.suggested_value,
                    reason=issue.description,
                )
                if self.apply_patch(patch):
                    result.patches_applied.append(patch)

        self._reconciliation_history.append(result)
        return result

    def reset_llm_failure_state(self) -> None:
        """Reset the LLM failure state to allow retry."""
        self.state.llm_failed = False
        self.state.waiting_for_input = False
        self.state.waiting_start_time = None
        self.state.last_updated = datetime.now(UTC).isoformat()
        logger.info("Reset LLM failure state")

    def inject_reconciliation_message(self, issues: list[ReconciliationIssue] | None = None) -> None:
        """Inject a reconciliation message into the conversation.

        This sends the current state summary to help the LLM understand
        where it is and what issues exist.
        """
        if issues is None:
            issues = self.check_for_issues()

        state_summary = self.get_state_as_text()

        issue_text = ""
        if issues:
            issue_lines = ["\n\nIDENTIFIED ISSUES:"]
            for issue in issues:
                issue_lines.append(
                    f"  - [{issue.severity.upper()}] {issue.issue_type.value}: {issue.description}"
                )
            issue_text = "\n".join(issue_lines)

        reconciliation_message = f"""<state_reconciliation>
<notice>This is an automatic state reconciliation checkpoint. Review the current state and identified issues, then continue appropriately.</notice>

{state_summary}
{issue_text}

<instructions>
Based on this state information:
1. Acknowledge any issues that need addressing
2. If you were in a loop or making repeated errors, try a different approach
3. If rate limits were hit, wait and retry with simpler requests
4. Continue with your task, keeping the state context in mind
</instructions>
</state_reconciliation>"""

        self.state.add_message("user", reconciliation_message)
        logger.info("Injected reconciliation message into conversation")

    def save_reconciliation_state(self, filepath: str) -> None:
        """Save the current reconciliation state to a JSON file."""
        state_data = {
            "state": self.get_complete_state_for_reconciliation(),
            "issues": [
                {
                    "issue_type": issue.issue_type.value,
                    "description": issue.description,
                    "field_path": issue.field_path,
                    "current_value": str(issue.current_value),
                    "suggested_value": str(issue.suggested_value),
                    "severity": issue.severity,
                    "auto_fixable": issue.auto_fixable,
                }
                for issue in self.check_for_issues()
            ],
            "history": [
                {
                    "timestamp": r.timestamp,
                    "issues_count": len(r.issues),
                    "patches_applied_count": len(r.patches_applied),
                    "success": r.success,
                }
                for r in self._reconciliation_history
            ],
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(state_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved reconciliation state to: {filepath}")
