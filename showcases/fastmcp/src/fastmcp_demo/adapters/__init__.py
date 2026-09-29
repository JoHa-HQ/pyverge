"""Adapters layer: FastMCP and OpenTelemetry integrations."""

from .server import build_discovery, build_lifespan, build_server
from .tracing import (
    CallSpanMiddleware,
    build_tracer,
    make_call_span_middleware,
    make_migration_hooks,
    make_tracer,
)

__all__ = [
    "CallSpanMiddleware",
    "build_discovery",
    "build_lifespan",
    "build_server",
    "build_tracer",
    "make_call_span_middleware",
    "make_migration_hooks",
    "make_tracer",
]
