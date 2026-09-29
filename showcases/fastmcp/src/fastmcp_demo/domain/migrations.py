"""Migration callables for the weather version graphs.

Each function is a plain ``(dict) -> dict`` transformation, the same shape
pyverge executes and whose AST the engine parses to reconstruct missing model
versions. They are grouped as documented tables so each graph reads as the
API's schema history::

    search_weather    v1 (temp) --add_humidity--> v2 (+humidity) --add_wind--> v3
    weather_briefing  v1 (city) --add_style--> v2 (+style)
    weather_reading   v1 (city) --add_units--> v2 (+units)
"""

from __future__ import annotations

from collections.abc import Callable

Migration = Callable[[dict], dict]


# -- search_weather (tool) ---------------------------------------------------


def add_humidity(data: dict) -> dict:
    """v1 -> v2: the API began reporting relative humidity."""
    return {**data, "humidity": 0}


def add_wind(data: dict) -> dict:
    """v2 -> v3: the API began reporting wind speed."""
    return {**data, "wind": 0.0}


def drop_wind(data: dict) -> dict:
    """v3 -> v2: discard wind for a caller on the older schema."""
    data = dict(data)
    del data["wind"]
    return data


def drop_humidity(data: dict) -> dict:
    """v2 -> v1: discard humidity for a caller on the oldest schema."""
    data = dict(data)
    del data["humidity"]
    return data


# -- weather_briefing (prompt) -----------------------------------------------


def add_style(data: dict) -> dict:
    """v1 -> v2: the prompt gained a wording style."""
    return {**data, "style": "short"}


def drop_style(data: dict) -> dict:
    """v2 -> v1: discard style for a caller on the older schema."""
    data = dict(data)
    del data["style"]
    return data


# -- weather_reading (resource) ----------------------------------------------


def add_units(data: dict) -> dict:
    """v1 -> v2: the resource gained a units parameter."""
    return {**data, "units": "celsius"}


def drop_units(data: dict) -> dict:
    """v2 -> v1: discard units for a caller on the older schema."""
    data = dict(data)
    del data["units"]
    return data
