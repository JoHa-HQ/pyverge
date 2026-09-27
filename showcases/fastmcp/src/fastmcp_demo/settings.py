"""Configuration for the FastMCP showcase.

Nested pydantic-settings models, mirroring the layout used across the codebase:
each concern is a ``BaseSettings`` with its own ``env_prefix`` and
``env_nested_delimiter="__"`` so the tree reads cleanly from environment
variables (e.g. ``FASTMCP_DEMO__TELEMETRY__OTLP_ENDPOINT``).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class TelemetrySettings(BaseSettings):
    """OpenTelemetry tracing configuration."""

    enabled: bool = Field(
        default=True,
        description="Build an OTLP tracer. False keeps the app export-free (tests).",
    )
    service_name: str = Field(default="pyverge-fastmcp-demo")
    otlp_endpoint: str = Field(
        default="http://localhost:4317",
        description="OTLP gRPC collector endpoint.",
    )

    model_config = SettingsConfigDict(
        env_prefix="TELEMETRY_",
        extra="ignore",
    )


class GraphSettings(BaseSettings):
    """The version graph the demo exposes."""

    kind: str = Field(default="search_weather")
    version_property: str = Field(default="version")
    kind_property: str = Field(default="kind")
    migrations_dir: Path = Field(default=PROJECT_ROOT / "migrations")
    policy: str = Field(
        default="latest",
        description="Target policy recorded for the kind on the registry.",
    )

    model_config = SettingsConfigDict(
        env_prefix="GRAPH_",
        extra="ignore",
    )


class DemoSettings(BaseSettings):
    """Root settings for the showcase application."""

    telemetry: TelemetrySettings = Field(default_factory=TelemetrySettings)
    graph: GraphSettings = Field(default_factory=GraphSettings)

    model_config = SettingsConfigDict(
        env_prefix="FASTMCP_DEMO_",
        env_nested_delimiter="__",
        extra="ignore",
    )
