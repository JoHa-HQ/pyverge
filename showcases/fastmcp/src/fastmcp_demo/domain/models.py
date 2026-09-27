"""The anchor model — the newest weather record, as a Pydantic model.

This is the source of truth for the v3 shape. Older versions are reconstructed
from it by the engine as each migration edge is registered; they are never
declared by hand.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SearchWeather(BaseModel):
    """Weather search result at the anchor version (v3).

    The fields mirror Open-Meteo's response schema as it grew: ``temperature``
    was always present, ``humidity`` arrived in v2, ``wind`` in v3.
    """

    kind: Literal["search_weather"] = "search_weather"
    version: Literal["3.0.0"] = "3.0.0"
    city: str
    units: str = "celsius"
    temperature: float = Field(default=0.0)
    humidity: int = Field(default=0)
    wind: float = Field(default=0.0)
