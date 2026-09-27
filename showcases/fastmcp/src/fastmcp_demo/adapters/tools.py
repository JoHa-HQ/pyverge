"""The FastMCP tool — a thin adapter over the injected ``WeatherService``.

The service arrives through dependency-injector wiring (``@inject`` +
``Provide``), so the tool owns no construction logic. The injected parameter is
hidden from the exposed signature: the physical tool signature *is* the anchor
model, and a stray parameter would break the adapter's signature/contract
reconciliation. Hiding it also keeps the reflected JSON schema clean for the
LLM client.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, TypeVar

from dependency_injector.wiring import Provide, inject

from ..domain.weather import WeatherService

_F = TypeVar("_F", bound=Callable[..., Any])


def hide_parameter(func: _F, name: str) -> _F:
    """Return *func* with *name* removed from its exposed signature.

    FastMCP reflects a tool's signature into its JSON schema and pyverge
    reconciles that schema against the registered model. An injected parameter
    is a wiring detail, not part of the contract, so it is stripped here.
    """
    signature = inspect.signature(func)
    func.__signature__ = signature.replace(  # ty: ignore[unresolved-attribute]
        parameters=[p for n, p in signature.parameters.items() if n != name]
    )
    return func


@inject
def search_weather(
    city: str,
    units: str = "celsius",
    humidity: bool = False,
    wind: float = 0.0,
    weather: WeatherService = Provide["weather_service"],
) -> dict:
    """Search weather for a city (anchor: v3).

    A call against an older schema (via a virtual tool) converges to this v3
    shape before the handler runs. ``weather`` is provided by the container.
    """
    return weather.forecast(city=city, units=units, humidity=humidity, wind=wind)


hide_parameter(search_weather, "weather")
