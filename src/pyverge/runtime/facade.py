from __future__ import annotations

from dataclasses import dataclass
from typing import Generic

from pyverge.core.engine import Engine
from pyverge.core.types import VersionValue

from .migrations import MigrationBindings


@dataclass(slots=True)
class Runtime(Generic[VersionValue]):
    """Application-time runtime owned by the manager.

    The runtime owns the binding store: callables and hooks live here, while
    the graph and registry keep metadata only.
    """

    engine: Engine[VersionValue]
    bindings: MigrationBindings[VersionValue]


__all__ = ["Runtime"]
