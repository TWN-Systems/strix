"""OpenTelemetry compatibility layer for Strix telemetry.

This module provides OpenTelemetry (OTEL) integration for distributed tracing,
allowing Strix to export traces to any OTEL-compatible backend (Jaeger, Zipkin,
Datadog, Honeycomb, etc.).

Features:
- Automatic trace/span creation from Strix events
- Semantic conventions for LLM observability
- Distributed trace context propagation
- Resource attributes for service identification
- Baggage for cross-service metadata

Usage:
    from strix.telemetry.opentelemetry import OTelCallback, setup_opentelemetry

    # Setup OpenTelemetry (reads from env vars)
    setup_opentelemetry(service_name="strix")

    # Add to tracer
    tracer = get_global_tracer()
    callback = OTelCallback()
    tracer.add_event_callback(callback.handle_event)

Environment Variables:
    OTEL_EXPORTER_OTLP_ENDPOINT: OTLP endpoint (e.g., http://localhost:4317)
    OTEL_EXPORTER_OTLP_HEADERS: Headers for OTLP exporter (key=value,key2=value2)
    OTEL_SERVICE_NAME: Service name (default: strix)
    OTEL_ENABLED: Enable/disable OTEL (default: true if endpoint set)
    STRIX_OTEL_CONSOLE_EXPORT: Export to console for debugging (default: false)
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Generator

from strix.telemetry.tracer import EventType, TracerEvent


if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Global OTEL state
_otel_initialized = False
_otel_tracer: Any = None
_otel_meter: Any = None


# Semantic conventions for LLM operations (following emerging OpenTelemetry GenAI conventions)
class SemanticAttributes:
    """Semantic attribute names for LLM observability."""

    # General
    SERVICE_NAME = "service.name"
    SERVICE_VERSION = "service.version"

    # LLM specific (following OpenTelemetry GenAI semantic conventions)
    LLM_SYSTEM = "gen_ai.system"
    LLM_REQUEST_MODEL = "gen_ai.request.model"
    LLM_RESPONSE_MODEL = "gen_ai.response.model"
    LLM_REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"
    LLM_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
    LLM_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
    LLM_USAGE_TOTAL_TOKENS = "gen_ai.usage.total_tokens"

    # Strix specific
    STRIX_SCAN_ID = "strix.scan.id"
    STRIX_AGENT_ID = "strix.agent.id"
    STRIX_AGENT_NAME = "strix.agent.name"
    STRIX_TOOL_NAME = "strix.tool.name"
    STRIX_VULN_SEVERITY = "strix.vulnerability.severity"
    STRIX_VULN_TITLE = "strix.vulnerability.title"


def _get_otel_modules() -> tuple[Any, ...] | None:
    """Lazily import OpenTelemetry modules."""
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
        from opentelemetry.sdk.resources import Resource

        return trace, TracerProvider, BatchSpanProcessor, ConsoleSpanExporter, Resource
    except ImportError:
        logger.warning(
            "OpenTelemetry not installed. Install with: "
            "pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp"
        )
        return None


def _get_otlp_exporter() -> Any | None:
    """Get the OTLP exporter if available."""
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        return OTLPSpanExporter
    except ImportError:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            return OTLPSpanExporter
        except ImportError:
            logger.warning(
                "OTLP exporter not installed. Install with: "
                "pip install opentelemetry-exporter-otlp-proto-grpc"
            )
            return None


def setup_opentelemetry(
    service_name: str = "strix",
    service_version: str = "0.3.5",
) -> bool:
    """Setup OpenTelemetry tracing.

    Args:
        service_name: Name of the service for traces
        service_version: Version of the service

    Returns:
        True if OpenTelemetry was successfully initialized
    """
    global _otel_initialized, _otel_tracer  # noqa: PLW0603

    if _otel_initialized:
        return True

    # Check if explicitly disabled
    enabled = os.getenv("OTEL_ENABLED", "").lower()
    if enabled == "false":
        logger.info("OpenTelemetry disabled via OTEL_ENABLED=false")
        return False

    # Get OTEL modules
    otel_modules = _get_otel_modules()
    if otel_modules is None:
        return False

    trace, TracerProvider, BatchSpanProcessor, ConsoleSpanExporter, Resource = otel_modules

    # Check if endpoint is configured
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    console_export = os.getenv("STRIX_OTEL_CONSOLE_EXPORT", "false").lower() == "true"

    if not endpoint and not console_export:
        if enabled == "true":
            logger.warning(
                "OTEL_ENABLED=true but OTEL_EXPORTER_OTLP_ENDPOINT not set"
            )
        return False

    try:
        # Create resource with service info
        resource = Resource.create({
            SemanticAttributes.SERVICE_NAME: os.getenv("OTEL_SERVICE_NAME", service_name),
            SemanticAttributes.SERVICE_VERSION: service_version,
        })

        # Create tracer provider
        provider = TracerProvider(resource=resource)

        # Add OTLP exporter if endpoint configured
        if endpoint:
            otlp_exporter_cls = _get_otlp_exporter()
            if otlp_exporter_cls:
                headers = _parse_otel_headers()
                exporter = otlp_exporter_cls(endpoint=endpoint, headers=headers)
                provider.add_span_processor(BatchSpanProcessor(exporter))
                logger.info(f"OpenTelemetry OTLP exporter configured: {endpoint}")

        # Add console exporter for debugging
        if console_export:
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
            logger.info("OpenTelemetry console exporter enabled")

        # Set as global provider
        trace.set_tracer_provider(provider)
        _otel_tracer = trace.get_tracer("strix", service_version)
        _otel_initialized = True

        logger.info("OpenTelemetry initialized successfully")
        return True

    except Exception as e:  # noqa: BLE001
        logger.warning(f"Failed to initialize OpenTelemetry: {e}")
        return False


def _parse_otel_headers() -> dict[str, str]:
    """Parse OTEL headers from environment variable."""
    headers_str = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "")
    if not headers_str:
        return {}

    headers = {}
    for pair in headers_str.split(","):
        if "=" in pair:
            key, value = pair.split("=", 1)
            headers[key.strip()] = value.strip()

    return headers


def get_otel_tracer() -> Any | None:
    """Get the OpenTelemetry tracer."""
    global _otel_tracer  # noqa: PLW0602
    if not _otel_initialized:
        setup_opentelemetry()
    return _otel_tracer


class OTelCallback:
    """Callback handler that sends tracer events to OpenTelemetry.

    This class translates Strix tracer events into OpenTelemetry spans
    with proper semantic attributes for LLM observability.
    """

    def __init__(self) -> None:
        """Initialize the OpenTelemetry callback handler."""
        self._spans: dict[str, Any] = {}  # span_key -> span context manager
        self._contexts: dict[str, Any] = {}  # span_key -> context token
        self._current_scan_span: Any = None

    @property
    def tracer(self) -> Any | None:
        """Get the OpenTelemetry tracer."""
        return get_otel_tracer()

    def handle_event(self, event: TracerEvent) -> None:
        """Handle a tracer event and send to OpenTelemetry.

        Args:
            event: The TracerEvent from the Strix tracer
        """
        if self.tracer is None:
            return

        try:
            handler = self._get_event_handler(event.event_type)
            if handler:
                handler(event)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"OpenTelemetry callback error for {event.event_type}: {e}")

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

    @contextmanager
    def _create_span(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
        parent_key: str | None = None,
    ) -> Generator[Any, None, None]:
        """Create a span with optional parent context."""
        from opentelemetry import trace

        # Get parent context if specified
        parent_span = self._spans.get(parent_key) if parent_key else None
        context = trace.set_span_in_context(parent_span) if parent_span else None

        with self.tracer.start_as_current_span(
            name,
            context=context,
            attributes=attributes or {},
        ) as span:
            yield span

    def _handle_scan_start(self, event: TracerEvent) -> None:
        """Create a root span for the scan."""
        run_id = event.data.get("run_id", "unknown")
        config = event.data.get("config", {})

        span = self.tracer.start_span(
            "strix.scan",
            attributes={
                SemanticAttributes.STRIX_SCAN_ID: run_id,
                "strix.scan.targets": str(config.get("targets", [])),
                "strix.scan.max_iterations": config.get("max_iterations", 200),
            },
        )

        self._spans["scan"] = span
        self._current_scan_span = span

    def _handle_scan_end(self, event: TracerEvent) -> None:
        """End the scan span."""
        span = self._spans.get("scan")
        if span:
            from opentelemetry.trace import StatusCode

            success = event.data.get("success", True)
            span.set_attribute("strix.scan.success", success)
            span.set_attribute(
                "strix.scan.vulnerabilities_found",
                event.data.get("vulnerabilities_found", 0),
            )

            if not success:
                span.set_status(StatusCode.ERROR, event.data.get("error", "Scan failed"))

            span.end()
            del self._spans["scan"]

    def _handle_agent_created(self, event: TracerEvent) -> None:
        """Create a span for the agent."""
        agent_id = event.agent_id
        if not agent_id:
            return

        # Determine parent (scan or parent agent)
        parent_id = event.data.get("parent_id")
        parent_key = f"agent:{parent_id}" if parent_id else "scan"

        parent_span = self._spans.get(parent_key)
        context = None
        if parent_span:
            from opentelemetry import trace
            context = trace.set_span_in_context(parent_span)

        span = self.tracer.start_span(
            f"agent:{event.data.get('name', agent_id)}",
            context=context,
            attributes={
                SemanticAttributes.STRIX_AGENT_ID: agent_id,
                SemanticAttributes.STRIX_AGENT_NAME: event.data.get("name", ""),
                "strix.agent.task": event.data.get("task", ""),
            },
        )

        self._spans[f"agent:{agent_id}"] = span

    def _handle_agent_completed(self, event: TracerEvent) -> None:
        """End the agent span."""
        agent_id = event.agent_id
        span_key = f"agent:{agent_id}"

        span = self._spans.get(span_key)
        if span:
            span.set_attribute("strix.agent.status", event.data.get("status", "completed"))
            span.end()
            del self._spans[span_key]

    def _handle_llm_request(self, event: TracerEvent) -> None:
        """Create a span for the LLM request."""
        agent_id = event.agent_id
        parent_key = f"agent:{agent_id}" if agent_id else "scan"

        parent_span = self._spans.get(parent_key)
        context = None
        if parent_span:
            from opentelemetry import trace
            context = trace.set_span_in_context(parent_span)

        model = event.data.get("model", "unknown")
        # Extract provider from model string (e.g., "anthropic/claude-sonnet-4")
        provider = model.split("/")[0] if "/" in model else "unknown"

        span = self.tracer.start_span(
            "llm.request",
            context=context,
            attributes={
                SemanticAttributes.LLM_SYSTEM: provider,
                SemanticAttributes.LLM_REQUEST_MODEL: model,
                "gen_ai.request.messages_count": event.data.get("messages_count", 0),
            },
        )

        self._spans[f"llm:{event.event_id}"] = span

    def _handle_llm_response(self, event: TracerEvent) -> None:
        """Complete the LLM span with response data."""
        request_event_id = event.data.get("request_event_id")
        span_key = f"llm:{request_event_id}"

        span = self._spans.get(span_key)
        if span:
            input_tokens = event.data.get("input_tokens", 0)
            output_tokens = event.data.get("output_tokens", 0)

            span.set_attribute(SemanticAttributes.LLM_USAGE_INPUT_TOKENS, input_tokens)
            span.set_attribute(SemanticAttributes.LLM_USAGE_OUTPUT_TOKENS, output_tokens)
            span.set_attribute(
                SemanticAttributes.LLM_USAGE_TOTAL_TOKENS,
                input_tokens + output_tokens,
            )
            span.set_attribute("gen_ai.usage.cached_tokens", event.data.get("cached_tokens", 0))

            if event.data.get("duration_ms"):
                span.set_attribute("gen_ai.response.duration_ms", event.data["duration_ms"])

            span.end()
            del self._spans[span_key]

    def _handle_llm_error(self, event: TracerEvent) -> None:
        """Handle LLM error."""
        request_event_id = event.data.get("request_event_id")
        span_key = f"llm:{request_event_id}"

        span = self._spans.get(span_key)
        if span:
            from opentelemetry.trace import StatusCode

            span.set_status(StatusCode.ERROR, event.data.get("error", "LLM error"))
            span.end()
            del self._spans[span_key]

    def _handle_tool_start(self, event: TracerEvent) -> None:
        """Create a span for tool execution."""
        agent_id = event.agent_id
        parent_key = f"agent:{agent_id}" if agent_id else "scan"

        parent_span = self._spans.get(parent_key)
        context = None
        if parent_span:
            from opentelemetry import trace
            context = trace.set_span_in_context(parent_span)

        tool_name = event.data.get("tool_name", "unknown")
        execution_id = event.data.get("execution_id")

        span = self.tracer.start_span(
            f"tool:{tool_name}",
            context=context,
            attributes={
                SemanticAttributes.STRIX_TOOL_NAME: tool_name,
                "strix.tool.execution_id": execution_id,
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
            if event.data.get("duration_ms"):
                span.set_attribute("strix.tool.duration_ms", event.data["duration_ms"])
            span.end()
            del self._spans[span_key]

    def _handle_tool_error(self, event: TracerEvent) -> None:
        """Handle tool error."""
        execution_id = event.data.get("execution_id")
        span_key = f"tool:{execution_id}" if execution_id else None

        if span_key and span_key in self._spans:
            from opentelemetry.trace import StatusCode

            span = self._spans[span_key]
            span.set_status(StatusCode.ERROR, event.data.get("error", "Tool error"))
            span.end()
            del self._spans[span_key]

    def _handle_vulnerability_found(self, event: TracerEvent) -> None:
        """Add vulnerability as an event on the scan span."""
        span = self._current_scan_span or self._spans.get("scan")
        if span:
            span.add_event(
                "vulnerability_found",
                attributes={
                    SemanticAttributes.STRIX_VULN_TITLE: event.data.get("title", ""),
                    SemanticAttributes.STRIX_VULN_SEVERITY: event.data.get("severity", ""),
                    "strix.vulnerability.id": event.data.get("vuln_id", ""),
                },
            )


def create_otel_callback() -> OTelCallback | None:
    """Create an OTelCallback if OpenTelemetry is configured.

    Returns:
        OTelCallback instance or None if OpenTelemetry is not configured
    """
    if setup_opentelemetry():
        return OTelCallback()
    return None
