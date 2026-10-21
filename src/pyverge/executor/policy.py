"""Execution policy: choose an executor from migration settings."""

from __future__ import annotations

import os

from pyverge.core.settings import MigrationSettings

from .parallel import AsyncLevelParallelExecutor, LevelParallelExecutor
from .sequential import AsyncSequentialExecutor, SequentialExecutor
from .types import AsyncExecutor, Executor


class ExecutionPolicy:
    """Build the executor implied by ``MigrationSettings``.

    - ``parallel_workers=0`` -> sequential
    - ``>0`` -> level-parallel, capped at ``os.cpu_count()``
    - ``execution_mode="sync"`` -> thread pool
    - ``execution_mode="async"`` -> ``asyncio.gather``
    """

    def __init__(self, settings: MigrationSettings) -> None:
        self._settings = settings

    @property
    def workers(self) -> int:
        """Configured worker count, capped at the CPU count."""
        workers = self._settings.parallel_workers
        if workers <= 0:
            return 0
        return min(workers, os.cpu_count() or 1)

    def build(self) -> Executor | AsyncExecutor:
        """Return the executor selected by the current settings."""
        workers = self.workers
        if self._settings.execution_mode == "async":
            if workers == 0:
                return AsyncSequentialExecutor()
            return AsyncLevelParallelExecutor(max_workers=workers)
        if workers == 0:
            return SequentialExecutor()
        return LevelParallelExecutor(max_workers=workers)
