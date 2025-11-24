"""Strix Telemetry - Observability and tracing infrastructure.

This package provides:
- Core event-based tracing (Tracer)
- Langfuse integration for LLM observability
- OpenTelemetry compatibility for distributed tracing

Usage:
    from strix.telemetry import Tracer, get_global_tracer, set_global_tracer

    # Basic usage
    tracer = Tracer(run_name="my-scan")
    set_global_tracer(tracer)  # Auto-initializes Langfuse/OTEL if configured

    # Manual Langfuse setup
    from strix.telemetry.langfuse import create_langfuse_callback
    callback = create_langfuse_callback()
    if callback:
        tracer.add_event_callback(callback.handle_event)

    # Manual OpenTelemetry setup
    from strix.telemetry.opentelemetry import create_otel_callback
    otel = create_otel_callback()
    if otel:
        tracer.add_event_callback(otel.handle_event)
"""

from strix.telemetry.tracer import (
    EventType,
    Tracer,
    TracerEvent,
    get_global_tracer,
    set_global_tracer,
)


__all__ = [
    "EventType",
    "Tracer",
    "TracerEvent",
    "get_global_tracer",
    "set_global_tracer",
]
