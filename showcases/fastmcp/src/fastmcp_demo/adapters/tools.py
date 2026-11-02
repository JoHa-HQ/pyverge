"""FastMCP primitives — thin adapters over the injected ``WeatherService``.

Three physical entities, one per FastMCP primitive type, each the newest
version of its kind:

* ``search_weather`` — the tool whose parameters form the v4 record,
* ``weather_briefing`` — the prompt that words the reading (v2),
* ``weather_reading`` — the resource template that serves the reading (v2).

The service arrives through FastMCP's native ``Depends``. The dependency
factory resolves the active demo container lazily, so the injected ``weather``
parameter is excluded from the reflected schema by FastMCP itself.
"""

from __future__ import annotations

from fastmcp.dependencies import Depends
from fastmcp.prompts import prompt
from fastmcp.resources.template import FunctionResourceTemplate
from fastmcp.tools import tool

from ..domain import ANCHOR_VERSION
from ..domain.weather import WeatherService

PROMPT_VERSION = "2.0.0"
RESOURCE_VERSION = "2.0.0"


def weather_service() -> WeatherService:
    """Resolve the active container's weather service for FastMCP Depends."""
    from ..container import current_weather_service  # noqa: PLC0415

    return current_weather_service()


@tool(name="search_weather", version=ANCHOR_VERSION)
def search_weather(  # noqa: PLR0913, PLR0917
    city: str,
    units: str = "celsius",
    temperature: float = 0.0,
    humidity: int = 0,
    wind: float = 0.0,
    coordinates: dict | None = None,
    weather: WeatherService = Depends(weather_service),
) -> dict:
    """Search weather for a city (anchor: v4).

    The parameters form the v4 weather record — an older caller's payload is
    converged to this shape before the handler runs, so ``temperature``,
    ``humidity``, ``wind`` and ``coordinates`` arrive populated. An explicit
    ``coordinates`` object bypasses geocoding; otherwise ``city`` is resolved.
    The handler refreshes the reading from the live Open-Meteo API and returns
    the current record. ``units`` selects the measurement system. ``weather`` is
    injected, not part of the payload.
    """
    latitude = longitude = None
    if coordinates:
        latitude = coordinates.get("latitude")
        longitude = coordinates.get("longitude")
    return weather.forecast(
        city=city, units=units, latitude=latitude, longitude=longitude
    )


@prompt(name="weather_briefing", version=PROMPT_VERSION)
def weather_briefing(
    city: str,
    style: str = "short",
    weather: WeatherService = Depends(weather_service),
) -> str:
    """A natural-language briefing for a city (anchor: v2).

    v1 took only ``city``; a v1 caller's payload is converged to include
    ``style`` before the handler runs. ``weather`` is injected, not payload.
    """
    reading = weather.forecast(city=city)
    if style == "detailed":
        return (
            f"{city}: {reading['temperature']:.1f}°, "
            f"{reading['humidity']}% humidity, {reading['wind']:.1f} km/h wind"
        )
    return f"{city}: {reading['temperature']:.1f}°"


def _weather_reading(
    city: str,
    units: str = "celsius",
    weather: WeatherService = Depends(weather_service),
) -> str:
    """The current reading for a city, as a resource (anchor: v2).

    v1 served only ``city``; a v1 caller's URI is converged to include
    ``units``. ``weather`` is injected, not payload.
    """
    reading = weather.forecast(city=city, units=units)
    return f"{city}: {reading['temperature']:.1f}° ({units})"


weather_reading = FunctionResourceTemplate.from_function(
    _weather_reading,
    uri_template="weather://{city}{?units}",
    name="weather_reading",
    version=RESOURCE_VERSION,
)
