from __future__ import annotations

from dataclasses import dataclass
from typing import Generic

from pyverge.core.engine import Engine
from pyverge.core.graph import MigrationGraph
from pyverge.core.types import VersionValue

from .factory import RunnerFactory, RunnerOptions
from .migrations import MigrationBindings
from .runner import Runner


@dataclass(slots=True)
class Runtime(Generic[VersionValue]):
    """Application-time runtime owned by the manager.

    The runtime owns the graph, the binding store, and the assembled runner.
    Callables and hooks live in the binding store; the graph and registry keep
    metadata only.
    """

    engine: Engine[VersionValue]
    bindings: MigrationBindings[VersionValue]
    graph: MigrationGraph[VersionValue] | None = None
    runner: Runner[VersionValue] | None = None

    def with_runner(self, options: RunnerOptions) -> Runtime[VersionValue]:
        graph = self.graph or self.engine.snapshot()
        runner = RunnerFactory().create(
            graph,
            self.bindings,
            self.engine.adapter,
            options=options,
        )
        return Runtime(
            engine=self.engine,
            bindings=self.bindings,
            graph=graph,
            runner=runner,
        )


__all__ = ["Runtime"]
