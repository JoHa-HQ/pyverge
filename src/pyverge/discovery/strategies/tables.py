"""Tables descriptor reflection."""

from __future__ import annotations

from .models import ModelSchemaStrategy


class TablesStrategy(ModelSchemaStrategy):
    """Register the models a table primitive declares."""


__all__ = ["TablesStrategy"]
