from __future__ import annotations

import pytest

from benchmarks.graphs import user_manager
from benchmarks.synthesis import payloads

VERSIONS = ("1.0.0", "2.0.0", "3.0.0")


@pytest.mark.parametrize("version", VERSIONS)
def test_synthesized_payloads_validate_against_source(version: str) -> None:
    """Guard: benchmark payloads must be valid instances of their source version.

    If a registered model drifts and synthesis no longer produces a valid
    instance, this fails the normal suite instead of poisoning benchmarks.
    """
    manager = user_manager()
    model = manager.get("User", version).model
    assert model is not None
    for payload in payloads(manager, "User", version, count=3):
        model.model_validate(payload)


def test_earliest_payload_migrates_to_latest() -> None:
    """Guard: the path benchmarks actually drive (earliest → latest) converges."""
    manager = user_manager()
    for payload in payloads(manager, "User", "1.0.0", count=3):
        manager.migrate(dict(payload), target="latest")
