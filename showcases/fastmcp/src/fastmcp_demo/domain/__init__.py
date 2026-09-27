"""Domain layer: the demo's version graph and weather service."""

from .graph import ALL_VERSIONS, V1, V2, V3, build_manager, schema
from .weather import CityNotFound, CurrentWeather, WeatherClient, WeatherService

#: The newest version — the physical tool's version, and the anchor older
#: versions are reconstructed from.
ANCHOR_VERSION = V3

__all__ = [
    "ALL_VERSIONS",
    "ANCHOR_VERSION",
    "V1",
    "V2",
    "V3",
    "CityNotFound",
    "CurrentWeather",
    "WeatherClient",
    "WeatherService",
    "build_manager",
    "schema",
]
