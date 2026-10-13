"""Schema-rigorous payload synthesis for benchmarks.

Payloads are generated from the registered models with Hypothesis
(``st.from_type``) and never hand-written, then serialized the way the adapter
does (``manager.dump``) and validated against the source model, so a benchmark
input is always a real instance of its version.
"""

from __future__ import annotations

from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from pyverge import Manager


def valid_instances(model: type, count: int) -> list[Any]:
    """Return up to *count* schema-valid instances of *model*, deterministically.

    ``derandomize`` keeps the corpus reproducible; ``database`` is disabled so
    runs are hermetic.
    """
    pool: list[Any] = []

    @settings(
        max_examples=count,
        derandomize=True,
        database=None,
        deadline=None,
        suppress_health_check=list(HealthCheck),
    )
    @given(st.from_type(model))
    def _collect(instance: Any) -> None:
        pool.append(instance)

    _collect()
    return pool


def payloads(
    manager: Manager,
    kind: str,
    version: str,
    *,
    count: int = 8,
) -> list[dict[str, Any]]:
    """Synthesize schema-valid payloads for ``kind@version``.

    Each payload is serialized from a generated instance and validated against
    the source version's model; an invalid one raises rather than being used.
    """
    model = manager.get(kind, version).model
    if model is None:
        raise ValueError(f"No concrete model registered for {kind}@{version}")

    result: list[dict[str, Any]] = []
    for instance in valid_instances(model, count):
        payload = manager.dump(instance)
        model.model_validate(payload)
        result.append(payload)
    return result


__all__ = ["payloads", "valid_instances"]
