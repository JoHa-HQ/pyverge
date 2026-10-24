"""Routes descriptor reflection."""

from __future__ import annotations

from .models import ModelSchemaStrategy


class RoutesStrategy(ModelSchemaStrategy):
    """Register the models a route primitive declares."""


__all__ = ["RoutesStrategy"]
