"""Celery worker lifecycle integration for a convergence runtime."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from celery.signals import worker_process_init, worker_process_shutdown

if TYPE_CHECKING:
    from pyverge.execution import Runner

from .runtime import CeleryRuntime

logger = logging.getLogger(__name__)


class CeleryLifecycle:
    """Bind and validate pyverge where Celery starts each worker process.

    Celery's signal dispatch catches ordinary exceptions and only logs them.
    A failed startup would therefore leave the worker alive with an unbound
    runtime. :meth:`startup` raises ``CeleryError`` for direct callers; the
    signal receiver converts startup failures to ``SystemExit`` so the child
    process exits before accepting tasks.
    """

    def __init__(
        self,
        runtime: CeleryRuntime,
        runner_factory: Callable[[], Runner],
        *,
        validate_health: bool = True,
        on_shutdown: Callable[[], None] | None = None,
    ) -> None:
        self._runtime = runtime
        self._runner_factory = runner_factory
        self._validate_health = validate_health
        self._on_shutdown = on_shutdown
        self._uid = f"pyverge.celery.lifecycle.{id(self)}"

    def install(self) -> None:
        """Connect pyverge startup and shutdown to Celery worker signals."""
        worker_process_init.connect(
            self._startup,
            weak=False,
            dispatch_uid=f"{self._uid}.init",
        )
        worker_process_shutdown.connect(
            self._shutdown,
            weak=False,
            dispatch_uid=f"{self._uid}.shutdown",
        )

    def uninstall(self) -> None:
        """Disconnect the pyverge receivers."""
        worker_process_init.disconnect(dispatch_uid=f"{self._uid}.init")
        worker_process_shutdown.disconnect(dispatch_uid=f"{self._uid}.shutdown")

    def startup(self, **kwargs: Any) -> None:
        """Build the runner, bind it, and validate registry health.

        Binding raises ``CeleryError`` when the registry fails the configured
        health level.

        Args:
            **kwargs: Celery signal context; ignored when called directly.
        """
        runner = self._runner_factory()
        self._runtime.bind(runner, validate_health=self._validate_health)

    def shutdown(self, **kwargs: Any) -> None:
        """Run the optional shutdown callback.

        Args:
            **kwargs: Celery signal context; ignored when called directly.
        """
        if self._on_shutdown is not None:
            self._on_shutdown()

    def _startup(self, **kwargs: Any) -> None:
        try:
            self.startup()
        except Exception as error:
            logger.exception("pyverge Celery startup failed: %s", error)
            raise SystemExit(1) from error

    def _shutdown(self, **kwargs: Any) -> None:
        try:
            self.shutdown()
        except Exception:
            logger.exception("pyverge Celery shutdown failed")


__all__ = ["CeleryLifecycle"]
