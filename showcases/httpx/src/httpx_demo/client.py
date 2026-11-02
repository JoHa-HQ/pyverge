"""httpx adapter composition: one runtime, one policy per transport."""

from __future__ import annotations

import semver

from pyverge import Manager
from pyverge.adapters.httpx import (
    HttpPolicy,
    PyvergeAsyncTransport,
    PyvergeTransport,
)
from pyverge.adapters.runtime import ConvergenceRuntime


def build_transport(
    manager: Manager[semver.Version], policy: HttpPolicy
) -> PyvergeTransport:
    """Build a sync transport, bind its runtime, and validate health."""
    transport = PyvergeTransport(ConvergenceRuntime(manager), policy=policy)
    transport.bind(manager.runner())
    return transport


def build_async_transport(
    manager: Manager[semver.Version], policy: HttpPolicy
) -> PyvergeAsyncTransport:
    """Build an async transport, bind its runtime, and validate health."""
    transport = PyvergeAsyncTransport(ConvergenceRuntime(manager), policy=policy)
    transport.bind(manager.runner())
    return transport


__all__ = ["build_async_transport", "build_transport"]
