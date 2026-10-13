"""Migration callables for the order version graph.

Each function is a plain ``(dict) -> dict`` transformation, the same shape
pyverge executes and whose AST the engine parses to reconstruct missing model
versions. The graph reads as the event's schema history::

    Order  v1 (total) --add_currency--> v2 (+currency)
"""

from __future__ import annotations

from collections.abc import Callable

Migration = Callable[[dict], dict]


def add_currency(data: dict) -> dict:
    """v1 -> v2: the event began carrying a currency."""
    return {**data, "currency": "USD"}


def drop_currency(data: dict) -> dict:
    """v2 -> v1: discard currency for a consumer pinned to the older schema."""
    data = dict(data)
    del data["currency"]
    return data
