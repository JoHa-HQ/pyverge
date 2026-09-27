"""The FastMCP tool — a thin adapter over the injected ``WeatherService``.

The service arrives through dependency-injector wiring (``@inject`` +
``Provide``), so the tool owns no construction logic. The injected parameter is
annotated ``Any`` and recognized by the adapter's injection detector
(``Provide`` marker), which excludes it from the reflected schema and the
reconciled contract — the tool needs no signature rewrite.
"""

from __future__ import annotations

from typing import Any

from dependency_injector.wiring import Provide, inject

from ..domain.weather import WeatherService


@inject
def search_weather(  # noqa: PLR0913
    city: str,
    units: str = "celsius",
    temperature: float = 0.0,
    humidity: int = 0,
    wind: float = 0.0,
    weather: Any = Provide["weather_service"],
) -> dict:
    """Search weather for a city (anchor: v3).

    The parameters form the v3 weather record — an older caller's payload is
    converged to this shape before the handler runs, so ``temperature``,
    ``humidity`` and ``wind`` arrive populated. The handler refreshes them from
    the live Open-Meteo API and returns the current reading. ``units`` selects
    the measurement system. ``weather`` is injected, not part of the payload.
    """
    service: WeatherService = weather
    return service.forecast(city=city, units=units)
