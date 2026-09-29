"""The anchor models — the newest shape of every versioned kind.

Each is the source of truth for its kind's newest version. Older versions are
reconstructed from the anchor by the engine as each migration edge is
registered; they are never declared by hand.

The demo exposes three kinds, one per FastMCP primitive type, so every
reflection provider (tool, prompt, resource) has a physical anchor:

* ``search_weather`` — the versioned *tool* whose arguments are the record,
* ``weather_briefing`` — the versioned *prompt* that words the reading,
* ``weather_reading`` — the versioned *resource* that serves the record.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Coordinates(BaseModel):
    """A resolved location at the anchor version (v1).

    A versioned nested kind: ``SearchWeather`` embeds it, so the engine
    converges the coordinates to their own target while the outer payload
    converges to the tool's target.
    """

    kind: Literal["coordinates"] = "coordinates"
    version: Literal["1.0.0"] = "1.0.0"
    latitude: float
    longitude: float


class SearchWeather(BaseModel):
    """Weather search result at the anchor version (v4).

    The fields mirror Open-Meteo's response schema as it grew: ``temperature``
    was always present, ``humidity`` arrived in v2, ``wind`` in v3, and the
    resolved ``coordinates`` in v4.
    """

    kind: Literal["search_weather"] = "search_weather"
    version: Literal["4.0.0"] = "4.0.0"
    city: str
    units: str = "celsius"
    temperature: float = Field(default=0.0)
    humidity: int = Field(default=0)
    wind: float = Field(default=0.0)
    coordinates: Coordinates | None = None


class WeatherBriefing(BaseModel):
    """Prompt arguments at the anchor version (v2).

    v1 took only ``city``; v2 added ``style`` for the wording.
    """

    kind: Literal["weather_briefing"] = "weather_briefing"
    version: Literal["2.0.0"] = "2.0.0"
    city: str
    style: str = "short"


class WeatherReading(BaseModel):
    """Resource parameters at the anchor version (v2).

    v1 served only ``city``; v2 added ``units``.
    """

    kind: Literal["weather_reading"] = "weather_reading"
    version: Literal["2.0.0"] = "2.0.0"
    city: str
    units: str = "celsius"
