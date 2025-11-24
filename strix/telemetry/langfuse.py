"""Langfuse integration for Strix telemetry.

This module provides a callback wrapper around the existing Tracer that sends
events to Langfuse for full observability. It integrates with ~100 lines of code
by leveraging the existing event-based tracer architecture.

Features:
- Automatic trace creation for scans
- Span tracking for agents, LLM calls, and tool executions
- Token usage and cost tracking
- Vulnerability finding annotations
- OpenTelemetry-compatible trace context

Usage:
    from strix.telemetry.langfuse import LangfuseCallback, setup_langfuse

    # Setup Langfuse (reads from env vars)
    langfuse = setup_langfuse()

    # Add to tracer
    tracer = get_global_tracer()
    callback = LangfuseCallback(langfuse)
    tracer.add_event_callback(callback.handle_event)

Environment Variables:
    LANGFUSE_PUBLIC_KEY: Your Langfuse public key
    LANGFUSE_SECRET_KEY: Your Langfuse secret key
    LANGFUSE_HOST: Langfuse host URL (default: https://cloud.langfuse.com)
    LANGFUSE_ENABLED: Enable/disable Langfuse (default: true if keys present)
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from strix.telemetry.tracer import EventType, TracerEvent


if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# Lazy import for Langfuse to avoid hard dependency
def _get_langfuse_client() -> Any:
    """Lazily import and return the Langfuse client class."""
    try:
        from langfuse import Langfuse

        return Langfuse
    except ImportError:
        logger.warning(
            "Langfuse not installed. Install with: pip install langfuse"
        )
        return None


class LangfuseCallback:
    """Callback handler that sends tracer events to Langfuse.

    This class wraps the existing Strix Tracer and translates its events
    into Langfuse traces, spans, and generations for full observability.
    """

    def __init__(self, langfuse_client: Any | None = None):
        """Initialize the Langfuse callback handler.

        Args:
            langfuse_client: An initialized Langfuse client instance.
                           If None, will attempt to create one from env vars.
        """
        self._langfuse = langfuse_client
        self._traces: dict[str, Any] = {}  # run_id -> trace
        self._spans: dict[str, Any] = {}  # span_key -> span
        self._generations: dict[str, Any] = {}  # request_event_id -> generation

        # Track context for correlation
        self._current_run_id: str | None = None
        self._agent_spans: dict[str, Any] = {}  # agent_id -> span

    @property
    def langfuse(self) -> Any | None:
        """Get the Langfuse client, initializing if needed."""
        if self._langfuse is None:
            self._langfuse = setup_langfuse()
        return self._langfuse

    def handle_event(self, event: TracerEvent) -> None:
        """Handle a tracer event and send to Langfuse.

        Args:
            event: The TracerEvent from the Strix tracer
        """
        if self.langfuse is None:
            return

        try:
            handler = self._get_event_handler(event.event_type)
            if handler:
                handler(event)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Langfuse callback error for {event.event_type}: {e}")

    def _get_event_handler(self, event_type: EventType) -> Any:
        """Get the handler function for an event type."""
        handlers = {
            EventType.SCAN_START: self._handle_scan_start,
            EventType.SCAN_END: self._handle_scan_end,
            EventType.AGENT_CREATED: self._handle_agent_created,
            EventType.AGENT_COMPLETED: self._handle_agent_completed,
            EventType.LLM_REQUEST: self._handle_llm_request,
            EventType.LLM_RESPONSE: self._handle_llm_response,
            EventType.LLM_ERROR: self._handle_llm_error,
            EventType.TOOL_START: self._handle_tool_start,
            EventType.TOOL_END: self._handle_tool_end,
            EventType.TOOL_ERROR: self._handle_tool_error,
            EventType.VULNERABILITY_FOUND: self._handle_vulnerability_found,
        }
        return handlers.get(event_type)

    def _handle_scan_start(self, event: TracerEvent) -> None:
        """Create a new Langfuse trace for the scan."""
        run_id = event.data.get("run_id", "unknown")
        config = event.data.get("config", {})

        trace = self.langfuse.trace(
            id=run_id,
            name="strix-scan",
            metadata={
                "targets": config.get("targets", []),
                "user_instructions": config.get("user_instructions", ""),
                "max_iterations": config.get("max_iterations", 200),
            },
            tags=["strix", "security-scan"],
        )

        self._traces[run_id] = trace
        self._current_run_id = run_id

    def _handle_scan_end(self, event: TracerEvent) -> None:
        """Complete the scan trace."""
        if self._current_run_id and self._current_run_id in self._traces:
            trace = self._traces[self._current_run_id]
            trace.update(
                metadata={
                    "success": event.data.get("success", True),
                    "vulnerabilities_found": event.data.get("vulnerabilities_found", 0),
                    "error": event.data.get("error"),
                }
            )
            self.langfuse.flush()

    def _handle_agent_created(self, event: TracerEvent) -> None:
        """Create a span for the agent."""
        agent_id = event.agent_id
        if not agent_id or not self._current_run_id:
            return

        trace = self._traces.get(self._current_run_id)
        if not trace:
            return

        # Check if parent agent exists
        parent_id = event.data.get("parent_id")
        parent_span = self._agent_spans.get(parent_id) if parent_id else None

        span = trace.span(
            name=event.data.get("name", agent_id),
            parent_observation_id=parent_span.id if parent_span else None,
            metadata={
                "task": event.data.get("task", ""),
                "agent_id": agent_id,
                "parent_agent_id": parent_id,
            },
        )

        self._agent_spans[agent_id] = span

    def _handle_agent_completed(self, event: TracerEvent) -> None:
        """Complete the agent span."""
        agent_id = event.agent_id
        if agent_id and agent_id in self._agent_spans:
            span = self._agent_spans[agent_id]
            span.end(
                metadata={
                    "status": event.data.get("status", "completed"),
                }
            )

    def _handle_llm_request(self, event: TracerEvent) -> None:
        """Create a generation for the LLM request."""
        agent_id = event.agent_id
        parent_span = self._agent_spans.get(agent_id) if agent_id else None

        trace = self._traces.get(self._current_run_id) if self._current_run_id else None
        if not trace:
            return

        generation = trace.generation(
            name="llm-request",
            parent_observation_id=parent_span.id if parent_span else None,
            model=event.data.get("model", "unknown"),
            metadata={
                "messages_count": event.data.get("messages_count", 0),
                "tokens_estimate": event.data.get("tokens_estimate"),
            },
        )

        self._generations[event.event_id] = generation

    def _handle_llm_response(self, event: TracerEvent) -> None:
        """Complete the LLM generation with response data."""
        request_event_id = event.data.get("request_event_id")
        if not request_event_id or request_event_id not in self._generations:
            return

        generation = self._generations[request_event_id]
        generation.end(
            usage={
                "input": event.data.get("input_tokens", 0),
                "output": event.data.get("output_tokens", 0),
                "total": (
                    event.data.get("input_tokens", 0) + event.data.get("output_tokens", 0)
                ),
            },
            metadata={
                "cached_tokens": event.data.get("cached_tokens", 0),
                "duration_ms": event.data.get("duration_ms"),
            },
        )

    def _handle_llm_error(self, event: TracerEvent) -> None:
        """Handle LLM error events."""
        request_event_id = event.data.get("request_event_id")
        if request_event_id and request_event_id in self._generations:
            generation = self._generations[request_event_id]
            generation.end(
                level="ERROR",
                status_message=event.data.get("error", "Unknown error"),
            )

    def _handle_tool_start(self, event: TracerEvent) -> None:
        """Create a span for tool execution."""
        agent_id = event.agent_id
        parent_span = self._agent_spans.get(agent_id) if agent_id else None

        trace = self._traces.get(self._current_run_id) if self._current_run_id else None
        if not trace:
            return

        tool_name = event.data.get("tool_name", "unknown")
        execution_id = event.data.get("execution_id")

        span = trace.span(
            name=f"tool:{tool_name}",
            parent_observation_id=parent_span.id if parent_span else None,
            input=event.data.get("args", {}),
            metadata={
                "tool_name": tool_name,
                "execution_id": execution_id,
            },
        )

        span_key = f"tool:{execution_id}" if execution_id else f"tool:{event.event_id}"
        self._spans[span_key] = span

    def _handle_tool_end(self, event: TracerEvent) -> None:
        """Complete the tool execution span."""
        execution_id = event.data.get("execution_id")
        span_key = f"tool:{execution_id}" if execution_id else None

        if span_key and span_key in self._spans:
            span = self._spans[span_key]
            span.end(
                output=event.data.get("result"),
                metadata={
                    "duration_ms": event.data.get("duration_ms"),
                },
            )

    def _handle_tool_error(self, event: TracerEvent) -> None:
        """Handle tool error events."""
        execution_id = event.data.get("execution_id")
        span_key = f"tool:{execution_id}" if execution_id else None

        if span_key and span_key in self._spans:
            span = self._spans[span_key]
            span.end(
                level="ERROR",
                status_message=event.data.get("error", "Unknown error"),
            )

    def _handle_vulnerability_found(self, event: TracerEvent) -> None:
        """Create an event for vulnerability findings."""
        trace = self._traces.get(self._current_run_id) if self._current_run_id else None
        if not trace:
            return

        trace.event(
            name="vulnerability-found",
            metadata={
                "title": event.data.get("title"),
                "severity": event.data.get("severity"),
                "vuln_id": event.data.get("vuln_id"),
            },
            level="WARNING" if event.data.get("severity") in ["low", "info"] else "ERROR",
        )

    def flush(self) -> None:
        """Flush all pending events to Langfuse."""
        if self.langfuse:
            self.langfuse.flush()

    def shutdown(self) -> None:
        """Shutdown the Langfuse client gracefully."""
        if self.langfuse:
            self.langfuse.shutdown()


def setup_langfuse() -> Any | None:
    """Setup and return a Langfuse client from environment variables.

    Environment Variables:
        LANGFUSE_PUBLIC_KEY: Your Langfuse public key
        LANGFUSE_SECRET_KEY: Your Langfuse secret key
        LANGFUSE_HOST: Langfuse host URL (default: https://cloud.langfuse.com)
        LANGFUSE_ENABLED: Enable/disable Langfuse (default: true if keys present)

    Returns:
        Langfuse client instance or None if not configured/disabled
    """
    # Check if explicitly disabled
    enabled = os.getenv("LANGFUSE_ENABLED", "").lower()
    if enabled == "false":
        logger.info("Langfuse disabled via LANGFUSE_ENABLED=false")
        return None

    # Get credentials
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")

    if not public_key or not secret_key:
        if enabled == "true":
            logger.warning(
                "LANGFUSE_ENABLED=true but missing LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY"
            )
        return None

    # Get Langfuse client class
    langfuse_cls = _get_langfuse_client()
    if langfuse_cls is None:
        return None

    # Create client
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

    try:
        client = langfuse_cls(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
        )
        logger.info(f"Langfuse initialized: {host}")
        return client
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Failed to initialize Langfuse: {e}")
        return None


def create_langfuse_callback() -> LangfuseCallback | None:
    """Create a LangfuseCallback if Langfuse is configured.

    Returns:
        LangfuseCallback instance or None if Langfuse is not configured
    """
    langfuse = setup_langfuse()
    if langfuse is None:
        return None
    return LangfuseCallback(langfuse)
