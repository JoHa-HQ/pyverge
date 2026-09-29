"""Domain layer: the demo's version graph and weather service."""

from . import migrations
from .graph import (
    ALL_VERSIONS,
    ANCHOR_MODEL,
    ANCHOR_MODELS,
    V1,
    V2,
    V3,
    build_manager,
)
from .models import SearchWeather, WeatherBriefing, WeatherReading
from .weather import CityNotFound, CurrentWeather, WeatherClient, WeatherService

#: The newest version — the physical tool's version, and the anchor older
#: versions are reconstructed from.
ANCHOR_VERSION = V3

__all__ = [
    "ALL_VERSIONS",
    "ANCHOR_MODEL",
    "ANCHOR_MODELS",
    "ANCHOR_VERSION",
    "V1",
    "V2",
    "V3",
    "CityNotFound",
    "CurrentWeather",
    "SearchWeather",
    "WeatherBriefing",
    "WeatherClient",
    "WeatherReading",
    "WeatherService",
    "build_manager",
    "migrations",
]
