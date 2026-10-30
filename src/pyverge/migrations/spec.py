from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pyverge.core.types import MigrationFunc
from pyverge.versioning import VersionPair


@dataclass(frozen=True, slots=True)
class MigrationSpec:
    """A normalized migration registration request."""

    pair: VersionPair[Any]
    func: MigrationFunc
    backward_compatible: bool = False


__all__ = ["MigrationSpec"]
