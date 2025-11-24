"""Automated Execution Pipeline for deterministic security testing.

This module provides a staged execution pipeline that:
1. Runs static/deterministic tools (scripts, nmap, etc.)
2. Generates reports from outputs
3. Has a planning agent review and create insights
4. Auto-completes plan items or replans as needed

Benefits:
- Efficiency: No LLM overhead for routine scans
- Determinism: Same inputs produce same outputs
- Reliability: Scripts are tested and validated
- Cost: Minimize expensive model calls

Usage:
    from strix.mcp.pipeline import ExecutionPipeline, PipelineStage

    pipeline = ExecutionPipeline()

    # Add reconnaissance stage
    pipeline.add_stage(PipelineStage(
        name="reconnaissance",
        scripts=["nmap_quick_scan", "whatweb_scan"],
        parameters={"target": "192.168.1.1"}
    ))

    # Execute pipeline
    results = await pipeline.execute()

    # Review with AI
    insights = await pipeline.review_with_ai(results)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from strix.mcp.gateway import MCPGateway

logger = logging.getLogger(__name__)


class StageStatus(str, Enum):
    """Status of a pipeline stage."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PlanItemStatus(str, Enum):
    """Status of a plan item."""

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"
    REPLANNED = "replanned"


@dataclass
class PlanItem:
    """A single item in the execution plan."""

    id: str
    description: str
    stage: str
    scripts: list[str] = field(default_factory=list)
    parameters: dict[str, str] = field(default_factory=dict)
    status: PlanItemStatus = PlanItemStatus.TODO
    result: dict[str, Any] | None = None
    dependencies: list[str] = field(default_factory=list)  # IDs of dependent items
    priority: int = 0
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "description": self.description,
            "stage": self.stage,
            "scripts": self.scripts,
            "parameters": self.parameters,
            "status": self.status.value,
            "result": self.result,
            "dependencies": self.dependencies,
            "priority": self.priority,
            "notes": self.notes,
        }


@dataclass
class PipelineStage:
    """A stage in the execution pipeline."""

    name: str
    scripts: list[str] = field(default_factory=list)
    parameters: dict[str, str] = field(default_factory=dict)
    parallel: bool = True  # Run scripts in parallel
    continue_on_error: bool = True
    timeout: int = 600
    status: StageStatus = StageStatus.PENDING
    results: list[dict[str, Any]] = field(default_factory=list)
    started_at: str | None = None
    completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "scripts": self.scripts,
            "parameters": self.parameters,
            "parallel": self.parallel,
            "continue_on_error": self.continue_on_error,
            "timeout": self.timeout,
            "status": self.status.value,
            "results": self.results,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


@dataclass
class PipelineResult:
    """Result of pipeline execution."""

    success: bool
    stages: list[dict[str, Any]]
    plan_items: list[dict[str, Any]]
    summary: str
    insights: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "stages": self.stages,
            "plan_items": self.plan_items,
            "summary": self.summary,
            "insights": self.insights,
            "recommendations": self.recommendations,
            "next_actions": self.next_actions,
            "duration_ms": self.duration_ms,
        }


class ExecutionPipeline:
    """Automated execution pipeline for security testing.

    Orchestrates deterministic script execution with AI-powered
    planning and review stages.
    """

    def __init__(self, mcp_gateway: MCPGateway | None = None):
        """Initialize the pipeline.

        Args:
            mcp_gateway: Optional MCP gateway for AI operations
        """
        self._mcp_gateway = mcp_gateway
        self._stages: list[PipelineStage] = []
        self._plan: list[PlanItem] = []
        self._next_item_id = 1

    @property
    def mcp_gateway(self) -> MCPGateway | None:
        """Get MCP gateway, initializing if needed."""
        if self._mcp_gateway is None:
            from strix.mcp.gateway import get_mcp_gateway
            self._mcp_gateway = get_mcp_gateway()
        return self._mcp_gateway

    def add_stage(self, stage: PipelineStage) -> None:
        """Add a stage to the pipeline."""
        self._stages.append(stage)

    def add_plan_item(
        self,
        description: str,
        stage: str,
        scripts: list[str] | None = None,
        parameters: dict[str, str] | None = None,
        dependencies: list[str] | None = None,
        priority: int = 0,
    ) -> PlanItem:
        """Add an item to the execution plan.

        Args:
            description: What this item accomplishes
            stage: Stage name (reconnaissance, scanning, etc.)
            scripts: Scripts to execute
            parameters: Script parameters
            dependencies: IDs of items this depends on
            priority: Execution priority (higher = first)

        Returns:
            The created PlanItem
        """
        item = PlanItem(
            id=f"plan-{self._next_item_id:04d}",
            description=description,
            stage=stage,
            scripts=scripts or [],
            parameters=parameters or {},
            dependencies=dependencies or [],
            priority=priority,
        )
        self._next_item_id += 1
        self._plan.append(item)
        return item

    def get_next_items(self) -> list[PlanItem]:
        """Get the next executable plan items.

        Returns items that:
        - Have status TODO
        - Have all dependencies satisfied
        - Are ordered by priority
        """
        completed_ids = {
            item.id for item in self._plan
            if item.status in (PlanItemStatus.DONE, PlanItemStatus.SKIPPED)
        }

        ready = []
        for item in self._plan:
            if item.status != PlanItemStatus.TODO:
                continue

            # Check dependencies
            deps_satisfied = all(
                dep_id in completed_ids for dep_id in item.dependencies
            )
            if deps_satisfied:
                ready.append(item)

        # Sort by priority (descending)
        ready.sort(key=lambda x: x.priority, reverse=True)
        return ready

    async def execute(self) -> PipelineResult:
        """Execute the pipeline stages.

        Returns:
            PipelineResult with all execution data
        """
        import time

        from strix.tools.scripts import get_scripts_registry

        start_time = time.monotonic()
        registry = get_scripts_registry()
        all_success = True

        # Execute each stage
        for stage in self._stages:
            stage.status = StageStatus.RUNNING
            stage.started_at = datetime.now(UTC).isoformat()
            stage.results = []

            try:
                if stage.parallel and len(stage.scripts) > 1:
                    # Run scripts in parallel
                    tasks = [
                        registry.execute(script, **stage.parameters)
                        for script in stage.scripts
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    for script, result in zip(stage.scripts, results):
                        if isinstance(result, Exception):
                            stage.results.append({
                                "script": script,
                                "success": False,
                                "error": str(result),
                            })
                            if not stage.continue_on_error:
                                all_success = False
                        else:
                            stage.results.append({
                                "script": script,
                                **result.to_dict(),
                            })
                            if not result.success and not stage.continue_on_error:
                                all_success = False
                else:
                    # Run scripts sequentially
                    for script in stage.scripts:
                        result = await registry.execute(script, **stage.parameters)
                        stage.results.append({
                            "script": script,
                            **result.to_dict(),
                        })
                        if not result.success and not stage.continue_on_error:
                            all_success = False
                            break

                stage.status = StageStatus.COMPLETED
            except Exception as e:  # noqa: BLE001
                logger.exception(f"Stage {stage.name} failed")
                stage.status = StageStatus.FAILED
                stage.results.append({"error": str(e)})
                all_success = False

            stage.completed_at = datetime.now(UTC).isoformat()

        duration_ms = int((time.monotonic() - start_time) * 1000)

        # Generate summary
        summary = self._generate_summary()

        return PipelineResult(
            success=all_success,
            stages=[s.to_dict() for s in self._stages],
            plan_items=[p.to_dict() for p in self._plan],
            summary=summary,
            duration_ms=duration_ms,
        )

    def _generate_summary(self) -> str:
        """Generate a text summary of execution results."""
        lines = ["# Pipeline Execution Summary\n"]

        for stage in self._stages:
            status_icon = {
                StageStatus.COMPLETED: "[OK]",
                StageStatus.FAILED: "[FAIL]",
                StageStatus.SKIPPED: "[SKIP]",
                StageStatus.RUNNING: "[RUN]",
                StageStatus.PENDING: "[PEND]",
            }.get(stage.status, "[?]")

            lines.append(f"\n## Stage: {stage.name} {status_icon}\n")

            for result in stage.results:
                script = result.get("script", "unknown")
                success = result.get("success", False)
                icon = "[OK]" if success else "[FAIL]"
                lines.append(f"- {script}: {icon}")

                if result.get("stdout"):
                    # Truncate long output
                    stdout = result["stdout"]
                    if len(stdout) > 500:
                        stdout = stdout[:500] + "...[truncated]"
                    lines.append(f"  ```\n  {stdout}\n  ```")

        return "\n".join(lines)

    async def review_with_ai(
        self,
        pipeline_result: PipelineResult,
    ) -> dict[str, Any]:
        """Review pipeline results with AI and generate insights.

        Uses the MCP gateway's thinkdeep and planner capabilities
        to analyze results and suggest next steps.

        Args:
            pipeline_result: Results from pipeline execution

        Returns:
            Dictionary with insights, recommendations, and next actions
        """
        if not self.mcp_gateway or not self.mcp_gateway.is_enabled:
            # Fallback to basic analysis without MCP
            return self._basic_analysis(pipeline_result)

        # Use thinkdeep for analysis
        analysis = await self.mcp_gateway.thinkdeep(
            prompt="""Analyze these security scan results and identify:
1. Key findings and potential vulnerabilities
2. Patterns or correlations across different scans
3. Areas that need deeper investigation
4. Potential attack vectors discovered""",
            context=pipeline_result.summary,
        )

        # Use planner for next steps
        plan = await self.mcp_gateway.planner(
            objective="Continue security assessment based on scan findings",
            context=f"""
Scan Results:
{pipeline_result.summary}

Analysis:
{analysis.data if analysis.success else 'Analysis not available'}
""",
            constraints=[
                "Prioritize high-impact findings",
                "Consider time and resource constraints",
                "Focus on actionable next steps",
            ],
        )

        # Extract insights
        insights = []
        recommendations = []
        next_actions = []

        if analysis.success and isinstance(analysis.data, str):
            insights = self._extract_bullet_points(analysis.data)

        if plan.success and isinstance(plan.data, dict):
            if "steps" in plan.data:
                next_actions = [step.get("description", str(step)) for step in plan.data["steps"]]
            if "recommendations" in plan.data:
                recommendations = plan.data["recommendations"]

        # Update pipeline result
        pipeline_result.insights = insights
        pipeline_result.recommendations = recommendations
        pipeline_result.next_actions = next_actions

        return {
            "success": True,
            "insights": insights,
            "recommendations": recommendations,
            "next_actions": next_actions,
            "analysis": analysis.data if analysis.success else None,
            "plan": plan.data if plan.success else None,
        }

    def _basic_analysis(self, result: PipelineResult) -> dict[str, Any]:
        """Basic analysis without MCP."""
        insights = []
        next_actions = []

        # Analyze each stage
        for stage in result.stages:
            for script_result in stage.get("results", []):
                if script_result.get("success"):
                    stdout = script_result.get("stdout", "")

                    # Basic pattern matching for common findings
                    if "open" in stdout.lower():
                        insights.append(f"Open ports detected in {script_result.get('script')}")
                    if "vulnerable" in stdout.lower():
                        insights.append(f"Potential vulnerability in {script_result.get('script')}")
                    if "http" in stdout.lower() or "https" in stdout.lower():
                        next_actions.append("Consider web application testing")

        if not insights:
            insights.append("Scan completed. Review detailed results for findings.")

        if not next_actions:
            next_actions.append("Review scan outputs and plan next steps")

        return {
            "success": True,
            "insights": insights,
            "recommendations": [],
            "next_actions": next_actions,
        }

    def _extract_bullet_points(self, text: str) -> list[str]:
        """Extract bullet points from text."""
        lines = text.split("\n")
        bullets = []
        for line in lines:
            line = line.strip()
            if line.startswith(("-", "*", "•", "1.", "2.", "3.")):
                # Remove bullet prefix
                content = line.lstrip("-*•0123456789. ")
                if content:
                    bullets.append(content)
        return bullets

    async def auto_complete_plan(self) -> list[PlanItem]:
        """Auto-complete ready plan items.

        Executes all plan items that are ready (dependencies satisfied)
        and updates their status.

        Returns:
            List of completed plan items
        """
        from strix.tools.scripts import get_scripts_registry

        registry = get_scripts_registry()
        completed = []

        while True:
            ready_items = self.get_next_items()
            if not ready_items:
                break

            for item in ready_items:
                item.status = PlanItemStatus.IN_PROGRESS

                try:
                    results = []
                    for script in item.scripts:
                        result = await registry.execute(script, **item.parameters)
                        results.append(result.to_dict())

                    item.result = {"scripts": results}
                    item.status = PlanItemStatus.DONE
                    completed.append(item)

                except Exception as e:  # noqa: BLE001
                    item.status = PlanItemStatus.BLOCKED
                    item.notes = f"Execution failed: {e}"
                    logger.warning(f"Plan item {item.id} failed: {e}")

        return completed

    async def replan(self, context: str) -> list[PlanItem]:
        """Replan based on new context or failures.

        Uses AI to analyze the current plan status and suggest
        adjustments based on what's been learned.

        Args:
            context: Additional context about why replanning is needed

        Returns:
            List of new/updated plan items
        """
        if not self.mcp_gateway or not self.mcp_gateway.is_enabled:
            logger.warning("MCP not available for replanning")
            return []

        # Get current plan status
        plan_summary = "\n".join([
            f"- {item.id}: {item.description} [{item.status.value}]"
            for item in self._plan
        ])

        # Get completed results
        completed_results = "\n".join([
            f"- {item.id}: {item.result}"
            for item in self._plan if item.result
        ])

        # Ask AI to replan
        result = await self.mcp_gateway.planner(
            objective="Adjust security testing plan based on current progress",
            context=f"""
Current Plan Status:
{plan_summary}

Completed Results:
{completed_results}

Replanning Context:
{context}
""",
            constraints=[
                "Keep what's working",
                "Address blockers and failures",
                "Prioritize based on findings so far",
            ],
        )

        new_items = []
        if result.success and isinstance(result.data, dict):
            for step in result.data.get("steps", []):
                # Mark existing item as replanned if referenced
                existing_id = step.get("replaces")
                if existing_id:
                    for item in self._plan:
                        if item.id == existing_id:
                            item.status = PlanItemStatus.REPLANNED
                            break

                # Add new plan item
                new_item = self.add_plan_item(
                    description=step.get("description", "New step"),
                    stage=step.get("stage", "utility"),
                    scripts=step.get("scripts", []),
                    parameters=step.get("parameters", {}),
                    priority=step.get("priority", 0),
                )
                new_items.append(new_item)

        return new_items


def create_reconnaissance_pipeline(
    target: str,
    quick: bool = True,
) -> ExecutionPipeline:
    """Create a standard reconnaissance pipeline.

    Args:
        target: Target IP or URL
        quick: If True, use quick scans. If False, use thorough scans.

    Returns:
        Configured ExecutionPipeline
    """
    pipeline = ExecutionPipeline()

    if quick:
        # Quick reconnaissance
        pipeline.add_stage(PipelineStage(
            name="port_discovery",
            scripts=["nmap_quick_scan"],
            parameters={"target": target},
        ))
        pipeline.add_stage(PipelineStage(
            name="web_fingerprint",
            scripts=["whatweb_scan"],
            parameters={"target": target},
        ))
    else:
        # Thorough reconnaissance
        pipeline.add_stage(PipelineStage(
            name="port_discovery",
            scripts=["nmap_full_scan"],
            parameters={"target": target},
            timeout=1800,
        ))
        pipeline.add_stage(PipelineStage(
            name="vulnerability_scan",
            scripts=["nmap_vuln_scan", "nikto_scan"],
            parameters={"target": target},
            timeout=1200,
        ))
        pipeline.add_stage(PipelineStage(
            name="directory_enum",
            scripts=["gobuster_dir", "ffuf_fuzz"],
            parameters={"target": target},
        ))

    return pipeline
