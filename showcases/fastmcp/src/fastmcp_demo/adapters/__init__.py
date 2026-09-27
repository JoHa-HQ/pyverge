"""Adapters layer: FastMCP and OpenTelemetry integrations."""

from .server import build_registry, build_server
from .tracing import build_tracer, make_tracer

__all__ = ["build_registry", "build_server", "build_tracer", "make_tracer"]
