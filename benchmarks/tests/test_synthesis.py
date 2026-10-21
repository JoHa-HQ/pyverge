from __future__ import annotations

import asyncio

import pytest

from benchmarks.graphs import user_manager
from benchmarks.synthesis import payloads
from pyverge.migration import MigrationSettings

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


@pytest.fixture
def benchmark_manager(request: pytest.FixtureRequest):
    """Build the benchmark manager with an explicit execution policy."""
    mode, workers = request.param
    settings = MigrationSettings(
        execution_mode=mode,
        parallel_workers=workers,
    )
    return user_manager(settings), mode


@pytest.mark.parametrize(
    "benchmark_manager",
    [
        pytest.param(("sync", 0), id="sync-sequential"),
        pytest.param(("sync", 2), id="sync-parallel"),
        pytest.param(("async", 0), id="async-sequential"),
        pytest.param(("async", 2), id="async-parallel"),
    ],
    indirect=True,
)
def test_earliest_payload_migrates_under_execution_policy(benchmark_manager) -> None:
    """Guard: benchmark path converges under every execution policy."""
    manager, mode = benchmark_manager
    for payload in payloads(manager, "User", "1.0.0", count=3):
        if mode == "async":
            result = asyncio.run(manager.amigrate(dict(payload), target="latest"))
        else:
            result = manager.migrate(dict(payload), target="latest")
        assert result["version"] == "3.0.0"
