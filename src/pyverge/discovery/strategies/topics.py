"""Topics descriptor reflection."""

from __future__ import annotations

from .models import ModelSchemaStrategy


class TopicsStrategy(ModelSchemaStrategy):
    """Register the models a topic primitive declares."""


__all__ = ["TopicsStrategy"]
