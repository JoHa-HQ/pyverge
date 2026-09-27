"""The tool's business logic — a plain service with no framework imports.

The FastMCP tool receives an instance of this via dependency-injector wiring,
so the handler stays a thin adapter over testable domain logic.
"""

from __future__ import annotations


class WeatherService:
    """Forecast lookup. In a real app this would call an upstream provider."""

    def forecast(
        self,
        city: str,
        units: str = "celsius",
        humidity: bool = False,
        wind: float = 0.0,
    ) -> dict:
        """Return the weather for *city* at the anchor (v3) shape."""
        return {
            "city": city,
            "units": units,
            "humidity": humidity,
            "wind": wind,
        }
