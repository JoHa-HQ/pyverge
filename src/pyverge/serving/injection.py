"""Injection detection — recognize parameters that are wired, not data.

A callable's signature is its contract: every parameter is a field the caller
may send. A dependency-injected parameter breaks that — it is wiring, not
payload — so the reflected schema must exclude it.

No DI library is imported eagerly: :func:`default_injection_detector` probes for
the markers of known libraries and falls back to a no-op. Detection is a plain
predicate over an ``inspect.Parameter``, so a host can supply its own.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import TypeAlias


def never_injected(parameter: inspect.Parameter) -> bool:
    """Default detector: no parameter is injected."""
    return False


def marker_detector(*marker_types: type) -> Callable[[inspect.Parameter], bool]:
    """Detect a parameter whose default is an instance of a marker type."""

    def detect(parameter: inspect.Parameter) -> bool:
        default = parameter.default
        if default is inspect.Parameter.empty:
            return False
        return isinstance(default, marker_types)

    return detect


def default_injection_detector() -> Callable[[inspect.Parameter], bool]:
    """Detect markers of the DI libraries pyverge sees in practice.

    Probes lazily so neither library is a hard dependency:

    * ``dependency_injector.wiring.Provide`` — a provider reference used as a
      parameter default by ``@inject``,
    * ``uncalled_for.Depends`` — FastMCP's own dependency marker.

    Returns :func:`never_injected` when neither is importable.
    """
    markers: list[type] = []
    try:  # pragma: no cover - import guard
        from dependency_injector.wiring import Provide  # noqa: PLC0415

        markers.append(Provide)  # ty: ignore[invalid-argument-type]
    except ImportError:
        pass
    try:  # pragma: no cover - import guard
        from uncalled_for import Depends  # noqa: PLC0415

        # ``Depends`` is a factory; the marker's class is the concrete result.
        markers.append(type(Depends(lambda: None)))
    except ImportError:
        pass
    if not markers:
        return never_injected
    return marker_detector(*markers)


InjectionDetector: TypeAlias = Callable[[inspect.Parameter], bool]
"""A predicate: ``True`` when a parameter is wired, not data."""


def injected_names(
    func: Callable[..., object], detector: InjectionDetector | None = None
) -> set[str]:
    """Return the names of the injected parameters of *func*.

    Returns an empty set when the signature is unavailable or nothing is
    injected.
    """
    detect = detector or default_injection_detector()
    try:
        parameters = inspect.signature(func).parameters
    except (TypeError, ValueError):
        return set()
    return {name for name, param in parameters.items() if detect(param)}


__all__ = [
    "InjectionDetector",
    "default_injection_detector",
    "injected_names",
    "marker_detector",
    "never_injected",
]
