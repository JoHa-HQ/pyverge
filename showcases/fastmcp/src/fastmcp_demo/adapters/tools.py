"""The FastMCP tool — a thin adapter over the injected ``WeatherService``.

The service arrives through dependency-injector wiring (``@inject`` +
``Provide``). The registered tool is built with
:func:`pyverge.adapters.fastmcp.make_tool`, which excludes the injected
parameter from the reflected schema — annotating it with its real type is fine,
because the factory hides it before FastMCP reflects the signature.
"""

from __future__ import annotations

from dependency_injector.wiring import Provide, inject

from ..domain.weather import WeatherService


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
