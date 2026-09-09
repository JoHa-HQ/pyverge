"""Pydantic model provider adapter.

:class:`PydanticModelAdapter` implements the :class:`ModelAdapter` protocol
for Pydantic models, and :class:`PydanticDiff` computes diffs between two
Pydantic model versions.
"""

from .adapter import PydanticDiff, PydanticModelAdapter

__all__ = ["PydanticDiff", "PydanticModelAdapter"]
