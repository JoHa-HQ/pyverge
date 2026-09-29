"""Weather domain: a real upstream client plus the tool's service.

``WeatherClient`` talks to Open-Meteo (keyless): geocode a city, then read the
current conditions. ``WeatherService`` returns the anchor (v4) response shape.

The version graph models the API's schema evolution: v1 returned only
``temperature``, v2 added ``humidity``, v3 added ``wind``, v4 added the resolved
``coordinates``. A caller sending an older-shaped payload has it converged
forward before the service refreshes the values from the live API. No framework
imports — dependency-injector wires the client into the service.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from ..settings import WeatherSettings

logger = logging.getLogger(__name__)


class CityNotFound(LookupError):
    """Raised when geocoding yields no match for a city."""


@dataclass(frozen=True)
class CurrentWeather:
    """A normalized current-conditions reading."""

    temperature: float
    humidity: int
    wind: float


class WeatherClient:
    """Open-Meteo client (geocoding + current forecast). Keyless."""

    def __init__(self, settings: WeatherSettings) -> None:
        self._settings = settings
        self._client = httpx.Client(timeout=settings.request_timeout)

    def close(self) -> None:
        self._client.close()

    def _geocode(self, city: str) -> tuple[float, float]:
        response = self._client.get(
            self._settings.geocode_url, params={"name": city, "count": 1}
        )
        response.raise_for_status()
        results = response.json().get("results") or []
        if not results:
            logger.warning("geocode found no match for %r", city)
            raise CityNotFound(city)
        match = results[0]
        return float(match["latitude"]), float(match["longitude"])

    def current(self, city: str, *, units: str = "celsius") -> CurrentWeather:
        """Return the current conditions for *city* in *units*."""
        latitude, longitude = self.resolve(city)
        return self.current_at(latitude, longitude, units=units)

    def resolve(self, city: str) -> tuple[float, float]:
        """Geocode *city* to ``(latitude, longitude)``."""
        return self._geocode(city)

    def current_at(
        self, latitude: float, longitude: float, *, units: str = "celsius"
    ) -> CurrentWeather:
        """Return the current conditions at *(latitude, longitude)* in *units*."""
        logger.debug("forecast @ (%.3f, %.3f) units=%s", latitude, longitude, units)
        temperature_unit, wind_unit = self._settings.unit_params[units]
        response = self._client.get(
            self._settings.forecast_url,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": self._settings.current_fields,
                "temperature_unit": temperature_unit,
                "wind_speed_unit": wind_unit,
            },
        )
        response.raise_for_status()
        current = response.json()["current"]
        return CurrentWeather(
            temperature=float(current["temperature_2m"]),
            humidity=int(current["relative_humidity_2m"]),
            wind=float(current["wind_speed_10m"]),
        )


class WeatherService:
    """Turn a city (or explicit coordinates) into the anchor (v4) shape."""

    def __init__(self, client: WeatherClient) -> None:
        self._client = client

    def forecast(
        self,
        city: str,
        units: str = "celsius",
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> dict:
        """Return the current conditions in the v4 shape.

        Explicit *latitude*/*longitude* bypass geocoding; otherwise the city is
        resolved. The record always reports the coordinates actually queried.
        """
        if latitude is not None and longitude is not None:
            coords = (latitude, longitude)
        else:
            coords = self._client.resolve(city)
        current = self._client.current_at(*coords, units=units)
        return {
            "city": city,
            "units": units,
            "temperature": current.temperature,
            "humidity": current.humidity,
            "wind": current.wind,
            "coordinates": {
                "kind": "coordinates",
                "version": "1.0.0",
                "latitude": coords[0],
                "longitude": coords[1],
            },
        }
