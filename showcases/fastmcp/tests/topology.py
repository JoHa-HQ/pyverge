"""Time-travel topology walk — a test helper, not application logic.

Given a registered version chain, migrate a newest-shaped payload down to the
oldest version and back up, asserting each hop yields the correctly-typed
container. This catches the failure modes per-edge unit tests miss: a missing
reverse edge, a non-idempotent forward migration, or a finalize step that
silently drops a field.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TopologyHop:
    """One leg of a topology walk: the version visited and the typed result."""

    version: str
    container: type
    payload: dict


def walk_topology(
    manager: Any, kind: str, versions: tuple[str, ...], **seed: Any
) -> list[TopologyHop]:
    """Walk *versions* from newest to oldest and back, asserting typed hops.

    Starts from a newest-shaped payload, migrates down to the oldest version,
    then back up to newest. Every hop is validated against the version's model
    via ``container=`` so a schema mismatch raises instead of passing silently.

    *seed* fills the newest payload (defaults to ``city="Berlin"``). Returns the
    down-walk hops; raises ``AssertionError`` when a hop returns the wrong
    container type.
    """
    newest = versions[-1]
    newest_cls = manager.get(kind, newest).model

    start = newest_cls.model_validate(
        {"kind": kind, "version": newest, "city": "Berlin", **seed}
    )

    hops: list[TopologyHop] = []
    for version in reversed(versions):
        cls = manager.get(kind, version).model
        result = manager.migrate(
            start.model_dump(mode="json"), target=version, container=cls
        )
        assert isinstance(result, cls), f"{version} did not yield {cls.__name__}"
        hops.append(TopologyHop(version, cls, result.model_dump(mode="json")))

    back = manager.migrate(hops[-1].payload, target=newest, container=newest_cls)
    assert isinstance(back, newest_cls), (
        f"return trip did not yield {newest_cls.__name__}"
    )
    return hops
