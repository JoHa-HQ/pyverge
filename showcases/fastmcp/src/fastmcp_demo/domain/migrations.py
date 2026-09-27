"""Migration callables for the weather version graph.

Each function is a plain ``(dict) -> dict`` transformation, the same shape
pyverge executes and whose AST the engine parses to reconstruct missing model
versions. They are grouped as a documented table so the graph reads as the
API's schema history::

    v1 (temperature) --add_humidity--> v2 (+humidity) --add_wind--> v3 (+wind)
"""

from __future__ import annotations

from collections.abc import Callable

Migration = Callable[[dict], dict]


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
