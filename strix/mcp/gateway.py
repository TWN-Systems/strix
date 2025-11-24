"""MCP Gateway for zen-mcp-server integration.

This module provides integration with zen-mcp-server, enabling:
- Multi-model consensus and validation
- Deep thinking and planning capabilities
- Code review and security audits
- External CLI integration (Gemini CLI, Codex CLI, Claude Code)

zen-mcp-server: https://github.com/BeehiveInnovations/zen-mcp-server

Usage:
    from strix.mcp import MCPGateway, get_mcp_gateway

    # Get the gateway (auto-initializes from env vars)
    gateway = get_mcp_gateway()

    # Use consensus for vulnerability validation
    result = await gateway.consensus(
        prompt="Is this SQL injection exploitable?",
        context=finding_details,
        models=["gemini-3.0-pro", "gpt-5-turbo", "claude-sonnet-4.5"]
    )

    # Deep thinking for complex analysis
    result = await gateway.thinkdeep(
        prompt="Analyze attack surface",
        context=scan_results
    )

Environment Variables:
    ZEN_MCP_ENABLED: Enable zen-mcp integration (default: false)
    ZEN_MCP_TRANSPORT: Transport type (stdio, http) - default: stdio
    ZEN_MCP_COMMAND: Command to start zen-mcp-server
    ZEN_MCP_URL: HTTP endpoint for zen-mcp (if using http transport)
    DEFAULT_MODEL: Default model for zen-mcp operations
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class MCPTool(str, Enum):
    """Available zen-mcp-server tools."""

    # Collaboration & Planning
    CLINK = "clink"  # Connect external CLIs
    CHAT = "chat"  # Multi-turn conversations
    THINKDEEP = "thinkdeep"  # Extended reasoning
    PLANNER = "planner"  # Project breakdown
    CONSENSUS = "consensus"  # Multi-model opinions

    # Code Quality
    CODEREVIEW = "codereview"  # Code reviews
    PRECOMMIT = "precommit"  # Pre-commit validation
    DEBUG = "debug"  # Root cause analysis

    # Development (may be disabled by default)
    ANALYZE = "analyze"
    REFACTOR = "refactor"
    TESTGEN = "testgen"
    SECAUDIT = "secaudit"
    DOCGEN = "docgen"

    # Utilities
    APILOOKUP = "apilookup"  # API documentation lookup
    CHALLENGE = "challenge"  # Critical analysis


@dataclass
class MCPConfig:
    """Configuration for MCP Gateway."""

    enabled: bool = False
    transport: str = "stdio"  # "stdio" or "http"
    command: list[str] = field(default_factory=list)
    url: str | None = None
    default_model: str = "gemini-3.0-pro"
    timeout: int = 120

    # Model preferences for different operations
    consensus_models: list[str] = field(default_factory=list)
    thinking_model: str = "gemini-3.0-pro"
    coding_model: str = "claude-sonnet-4-20250514"

    @classmethod
    def from_env(cls) -> MCPConfig:
        """Create configuration from environment variables."""
        enabled = os.getenv("ZEN_MCP_ENABLED", "false").lower() == "true"

        # Default command to run zen-mcp-server
        command_str = os.getenv("ZEN_MCP_COMMAND", "npx -y @anthropic/zen-mcp-server")
        command = command_str.split() if command_str else []

        # Consensus models from comma-separated list
        consensus_str = os.getenv(
            "ZEN_MCP_CONSENSUS_MODELS",
            "gemini-3.0-pro,gpt-5-turbo,claude-sonnet-4-20250514"
        )
        consensus_models = [m.strip() for m in consensus_str.split(",") if m.strip()]

        return cls(
            enabled=enabled,
            transport=os.getenv("ZEN_MCP_TRANSPORT", "stdio"),
            command=command,
            url=os.getenv("ZEN_MCP_URL"),
            default_model=os.getenv("DEFAULT_MODEL", "gemini-3.0-pro"),
            timeout=int(os.getenv("ZEN_MCP_TIMEOUT", "120")),
            consensus_models=consensus_models,
            thinking_model=os.getenv("ZEN_MCP_THINKING_MODEL", "gemini-3.0-pro"),
            coding_model=os.getenv("ZEN_MCP_CODING_MODEL", "claude-sonnet-4-20250514"),
        )


@dataclass
class MCPResult:
    """Result from an MCP tool call."""

    success: bool
    data: Any = None
    error: str | None = None
    tool: str | None = None
    models_used: list[str] = field(default_factory=list)
    consensus_score: float | None = None  # Agreement level for consensus calls

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "tool": self.tool,
            "models_used": self.models_used,
            "consensus_score": self.consensus_score,
        }


class MCPGateway:
    """Gateway for zen-mcp-server integration.

    Provides high-level methods for common MCP operations like
    consensus, deep thinking, planning, and code review.
    """

    def __init__(self, config: MCPConfig | None = None):
        """Initialize the MCP Gateway.

        Args:
            config: MCP configuration. If None, loads from environment.
        """
        self.config = config or MCPConfig.from_env()
        self._process: subprocess.Popen[bytes] | None = None
        self._request_id = 0

    @property
    def is_enabled(self) -> bool:
        """Check if MCP is enabled."""
        return self.config.enabled

    async def _call_tool(
        self,
        tool: str | MCPTool,
        arguments: dict[str, Any],
    ) -> MCPResult:
        """Call an MCP tool.

        Args:
            tool: Tool name or MCPTool enum
            arguments: Tool arguments

        Returns:
            MCPResult with the tool response
        """
        if not self.is_enabled:
            return MCPResult(
                success=False,
                error="MCP Gateway is not enabled. Set ZEN_MCP_ENABLED=true",
                tool=str(tool),
            )

        tool_name = tool.value if isinstance(tool, MCPTool) else tool

        try:
            if self.config.transport == "stdio":
                return await self._call_via_stdio(tool_name, arguments)
            elif self.config.transport == "http":
                return await self._call_via_http(tool_name, arguments)
            else:
                return MCPResult(
                    success=False,
                    error=f"Unknown transport: {self.config.transport}",
                    tool=tool_name,
                )
        except Exception as e:  # noqa: BLE001
            logger.exception(f"MCP tool call failed: {tool_name}")
            return MCPResult(
                success=False,
                error=str(e),
                tool=tool_name,
            )

    async def _call_via_stdio(
        self,
        tool: str,
        arguments: dict[str, Any],
    ) -> MCPResult:
        """Call MCP tool via stdio transport."""
        if self._process is None:
            await self._start_process()

        if self._process is None:
            return MCPResult(
                success=False,
                error="Failed to start MCP server process",
                tool=tool,
            )

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "tools/call",
            "params": {
                "name": tool,
                "arguments": arguments,
            },
        }

        try:
            # Write request
            request_bytes = (json.dumps(request) + "\n").encode()
            self._process.stdin.write(request_bytes)  # type: ignore[union-attr]
            self._process.stdin.flush()  # type: ignore[union-attr]

            # Read response with timeout
            response_line = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    self._process.stdout.readline,  # type: ignore[union-attr]
                ),
                timeout=self.config.timeout,
            )

            response = json.loads(response_line.decode())

            if "error" in response:
                return MCPResult(
                    success=False,
                    error=response["error"].get("message", "Unknown error"),
                    tool=tool,
                )

            result = response.get("result", {})
            return MCPResult(
                success=True,
                data=result.get("content", result),
                tool=tool,
            )

        except asyncio.TimeoutError:
            return MCPResult(
                success=False,
                error=f"MCP call timed out after {self.config.timeout}s",
                tool=tool,
            )

    async def _call_via_http(
        self,
        tool: str,
        arguments: dict[str, Any],
    ) -> MCPResult:
        """Call MCP tool via HTTP transport."""
        if not self.config.url:
            return MCPResult(
                success=False,
                error="ZEN_MCP_URL not configured for HTTP transport",
                tool=tool,
            )

        try:
            import httpx

            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.post(
                    f"{self.config.url}/tools/call",
                    json={
                        "name": tool,
                        "arguments": arguments,
                    },
                )
                response.raise_for_status()
                data = response.json()

                return MCPResult(
                    success=True,
                    data=data.get("content", data),
                    tool=tool,
                )

        except ImportError:
            return MCPResult(
                success=False,
                error="httpx not installed. Run: pip install httpx",
                tool=tool,
            )
        except Exception as e:  # noqa: BLE001
            return MCPResult(
                success=False,
                error=str(e),
                tool=tool,
            )

    async def _start_process(self) -> None:
        """Start the MCP server process."""
        if not self.config.command:
            logger.error("No MCP server command configured")
            return

        try:
            self._process = subprocess.Popen(
                self.config.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            logger.info(f"Started MCP server: {' '.join(self.config.command)}")
        except (OSError, subprocess.SubprocessError) as e:
            logger.error(f"Failed to start MCP server: {e}")
            self._process = None

    async def consensus(
        self,
        prompt: str,
        context: str | None = None,
        models: list[str] | None = None,
        stance: str | None = None,
    ) -> MCPResult:
        """Get consensus from multiple AI models.

        Args:
            prompt: The question or analysis request
            context: Additional context for the models
            models: List of models to query (default: from config)
            stance: Optional stance steering ("skeptical", "optimistic", etc.)

        Returns:
            MCPResult with consensus analysis and score
        """
        models = models or self.config.consensus_models

        arguments = {
            "prompt": prompt,
            "models": models,
        }
        if context:
            arguments["context"] = context
        if stance:
            arguments["stance"] = stance

        result = await self._call_tool(MCPTool.CONSENSUS, arguments)
        result.models_used = models

        # Extract consensus score if available
        if result.success and isinstance(result.data, dict):
            result.consensus_score = result.data.get("agreement_score")

        return result

    async def thinkdeep(
        self,
        prompt: str,
        context: str | None = None,
        model: str | None = None,
    ) -> MCPResult:
        """Extended reasoning and edge case analysis.

        Args:
            prompt: The problem or question to analyze
            context: Additional context
            model: Model to use (default: thinking_model from config)

        Returns:
            MCPResult with deep analysis
        """
        model = model or self.config.thinking_model

        arguments = {
            "prompt": prompt,
            "model": model,
        }
        if context:
            arguments["context"] = context

        result = await self._call_tool(MCPTool.THINKDEEP, arguments)
        result.models_used = [model]
        return result

    async def planner(
        self,
        objective: str,
        context: str | None = None,
        constraints: list[str] | None = None,
    ) -> MCPResult:
        """Break down complex projects into actionable steps.

        Args:
            objective: The goal to plan for
            context: Current situation and constraints
            constraints: List of constraints to consider

        Returns:
            MCPResult with structured plan
        """
        arguments = {"objective": objective}
        if context:
            arguments["context"] = context
        if constraints:
            arguments["constraints"] = constraints

        return await self._call_tool(MCPTool.PLANNER, arguments)

    async def codereview(
        self,
        code: str,
        language: str | None = None,
        focus: list[str] | None = None,
    ) -> MCPResult:
        """Professional code review with severity levels.

        Args:
            code: The code to review
            language: Programming language
            focus: Areas to focus on (e.g., ["security", "performance"])

        Returns:
            MCPResult with review findings
        """
        arguments = {"code": code}
        if language:
            arguments["language"] = language
        if focus:
            arguments["focus"] = focus

        return await self._call_tool(MCPTool.CODEREVIEW, arguments)

    async def secaudit(
        self,
        code: str,
        context: str | None = None,
    ) -> MCPResult:
        """Security audit of code.

        Args:
            code: The code to audit
            context: Additional context about the application

        Returns:
            MCPResult with security findings
        """
        arguments = {"code": code}
        if context:
            arguments["context"] = context

        return await self._call_tool(MCPTool.SECAUDIT, arguments)

    async def debug(
        self,
        problem: str,
        code: str | None = None,
        error: str | None = None,
    ) -> MCPResult:
        """Systematic investigation and root cause analysis.

        Args:
            problem: Description of the problem
            code: Relevant code
            error: Error message or stack trace

        Returns:
            MCPResult with debug analysis
        """
        arguments = {"problem": problem}
        if code:
            arguments["code"] = code
        if error:
            arguments["error"] = error

        return await self._call_tool(MCPTool.DEBUG, arguments)

    async def apilookup(
        self,
        query: str,
        technology: str | None = None,
    ) -> MCPResult:
        """Look up current API/SDK documentation.

        Args:
            query: What to look up
            technology: Specific technology (e.g., "python", "nodejs")

        Returns:
            MCPResult with documentation info
        """
        arguments = {"query": query}
        if technology:
            arguments["technology"] = technology

        return await self._call_tool(MCPTool.APILOOKUP, arguments)

    async def challenge(
        self,
        claim: str,
        context: str | None = None,
    ) -> MCPResult:
        """Critical analysis to prevent reflexive agreement.

        Args:
            claim: The claim or assumption to challenge
            context: Additional context

        Returns:
            MCPResult with critical analysis
        """
        arguments = {"claim": claim}
        if context:
            arguments["context"] = context

        return await self._call_tool(MCPTool.CHALLENGE, arguments)

    async def clink(
        self,
        cli: str,
        command: str,
        context: str | None = None,
    ) -> MCPResult:
        """Connect to external CLI (Gemini CLI, Codex CLI, Claude Code).

        Args:
            cli: CLI to connect to
            command: Command to execute
            context: Context to pass

        Returns:
            MCPResult with CLI output
        """
        arguments = {
            "cli": cli,
            "command": command,
        }
        if context:
            arguments["context"] = context

        return await self._call_tool(MCPTool.CLINK, arguments)

    def shutdown(self) -> None:
        """Shutdown the MCP server process."""
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
            logger.info("MCP server process terminated")


# Global gateway instance
_global_gateway: MCPGateway | None = None


def get_mcp_gateway() -> MCPGateway:
    """Get the global MCP Gateway instance."""
    global _global_gateway  # noqa: PLW0603

    if _global_gateway is None:
        _global_gateway = MCPGateway()

    return _global_gateway


def set_mcp_gateway(gateway: MCPGateway) -> None:
    """Set the global MCP Gateway instance."""
    global _global_gateway  # noqa: PLW0603
    _global_gateway = gateway
