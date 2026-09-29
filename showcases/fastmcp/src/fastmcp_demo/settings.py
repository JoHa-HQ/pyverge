"""Configuration for the FastMCP showcase.

Nested pydantic-settings models, mirroring the layout used across the codebase:
each concern is a ``BaseSettings`` with its own ``env_prefix`` and
``env_nested_delimiter="__"`` so the tree reads cleanly from environment
variables (e.g. ``FASTMCP_DEMO__TELEMETRY__OTLP_ENDPOINT``).
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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


class WeatherSettings(BaseSettings):
    """Upstream Open-Meteo endpoints and query parameters."""

    geocode_url: str = Field(
        default="https://geocoding-api.open-meteo.com/v1/search",
        description="Geocoding endpoint resolving a city name to coordinates.",
    )
    forecast_url: str = Field(
        default="https://api.open-meteo.com/v1/forecast",
        description="Current-conditions forecast endpoint.",
    )
    current_fields: str = Field(
        default="temperature_2m,relative_humidity_2m,wind_speed_10m",
        description="Comma-separated Open-Meteo `current` fields to request.",
    )

    #: Query ``units`` value -> (temperature_unit, wind_speed_unit). A fixed,
    #: structural mapping (not operator config), so it stays a plain constant.
    unit_params: dict[str, tuple[str, str]] = Field(
        default_factory=lambda: {
            "celsius": ("celsius", "kmh"),
            "fahrenheit": ("fahrenheit", "mph"),
        },
        exclude=True,
    )
    request_timeout: float = Field(
        default=10.0,
        description="HTTP request timeout in seconds.",
    )

    model_config = SettingsConfigDict(
        env_prefix="WEATHER_",
        extra="ignore",
    )


class GraphSettings(BaseSettings):
    """The version graph the demo exposes."""

    kind: str = Field(
        default="search_weather",
        description="The anchor kind (the versioned tool).",
    )
    version_property: str = Field(default="version")
    kind_property: str = Field(default="kind")
    policies: dict[str, str] = Field(
        default_factory=lambda: {
            "search_weather": "latest",
            "weather_briefing": "latest",
            "weather_reading": "latest",
        },
        description="Target policy recorded per versioned kind.",
    )

    model_config = SettingsConfigDict(
        env_prefix="GRAPH_",
        extra="ignore",
    )


class ServerSettings(BaseSettings):
    """HTTP transport binding for the MCP server."""

    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8001)
    path: str = Field(default="/mcp", description="HTTP path serving MCP.")
    search_enabled: bool = Field(
        default=True,
        description="Expose the BM25 search transform (search_tools + call_tool).",
    )
    search_tool_name: str = Field(default="search_tools")
    search_max_results: int = Field(default=5)

    model_config = SettingsConfigDict(
        env_prefix="SERVER_",
        extra="ignore",
    )


class DemoSettings(BaseSettings):
    """Root settings for the showcase application."""

    telemetry: TelemetrySettings = Field(default_factory=TelemetrySettings)
    weather: WeatherSettings = Field(default_factory=WeatherSettings)
    graph: GraphSettings = Field(default_factory=GraphSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    log_level: str = Field(
        default="INFO",
        description="Root log level for the demo (e.g. DEBUG, INFO, WARNING).",
    )

    model_config = SettingsConfigDict(
        env_prefix="FASTMCP_DEMO_",
        env_nested_delimiter="__",
        extra="ignore",
    )
