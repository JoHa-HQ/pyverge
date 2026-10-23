"""Migration-local type surface: execution/transport protocols and entry types.

These reference the migration graph and registry, so they belong to the
migration package rather than the provider-neutral core type module.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, Protocol

from pyverge.core.types import (
    VersionValue,
)

if TYPE_CHECKING:
    from pyverge.core.versioning import VersionNode

    from .registry import Registry

#: A discovered versioned entry: ``(path, depth, source)``.
Entry = tuple[tuple[str | int, ...], int, "VersionNode[VersionValue]"]


class Walker(Protocol[VersionValue]):
    """Protocol for schema-aware payload discovery."""

    @property
    def registry(self) -> Registry[VersionValue]: ...

    def discover(
        self,
        data: dict[str, Any],
        *,
        container: type[Any] | None = None,
        target_resolver: Any,
        max_depth: int = -1,
    ) -> Iterator[Entry]: ...
