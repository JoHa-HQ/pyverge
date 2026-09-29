"""FastMCP primitives — thin adapters over the injected ``WeatherService``.

Three physical entities, one per FastMCP primitive type, each the newest
version of its kind:

* ``search_weather`` — the tool whose parameters form the v3 record,
* ``weather_briefing`` — the prompt that words the reading (v2),
* ``weather_reading`` — the resource template that serves the reading (v2).

The service arrives through dependency-injector wiring (``@inject`` +
``Provide``). Each function is wrapped by the adapter's ``tool``/``prompt``/
``resource`` decorator, applied **outside** ``@inject``, so the injected
``weather`` parameter is hidden before FastMCP reflects the signature — a
caller never sees it, but the handler still receives it at call time.
"""

from __future__ import annotations

from dependency_injector.wiring import Provide, inject

from pyverge.adapters.fastmcp import prompt, resource, tool

from ..domain import ANCHOR_VERSION
from ..domain.weather import WeatherService

PROMPT_VERSION = "2.0.0"
RESOURCE_VERSION = "2.0.0"


@tool(name="search_weather", version=ANCHOR_VERSION)
@inject
def search_weather(  # noqa: PLR0913
    city: str,
    units: str = "celsius",
    temperature: float = 0.0,
    humidity: int = 0,
    wind: float = 0.0,
    weather: WeatherService = Provide["weather_service"],
) -> dict:
    """Search weather for a city (anchor: v3).

    The parameters form the v3 weather record — an older caller's payload is
    converged to this shape before the handler runs, so ``temperature``,
    ``humidity`` and ``wind`` arrive populated. The handler refreshes them from
    the live Open-Meteo API and returns the current reading. ``units`` selects
    the measurement system. ``weather`` is injected, not part of the payload.
    """
    return weather.forecast(city=city, units=units)


@prompt(name="weather_briefing", version=PROMPT_VERSION)
@inject
def weather_briefing(
    city: str,
    style: str = "short",
    weather: WeatherService = Provide["weather_service"],
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


@resource(
    uri_template="weather://{city}{?units}",
    name="weather_reading",
    version=RESOURCE_VERSION,
)
@inject
def weather_reading(
    city: str,
    units: str = "celsius",
    weather: WeatherService = Provide["weather_service"],
) -> str:
    """The current reading for a city, as a resource (anchor: v2).

    v1 served only ``city``; a v1 caller's URI is converged to include
    ``units``. ``weather`` is injected, not payload.
    """
    reading = weather.forecast(city=city, units=units)
    return f"{city}: {reading['temperature']:.1f}° ({units})"
