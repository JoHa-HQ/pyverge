"""Schema migration graph benchmarks."""

from __future__ import annotations

import pytest

from pyverge.jgf import JgfExporter
from pyverge.versioning import default_content_hasher
from tests.benchmarks.migrations._support import build_chain, payload

pytestmark = pytest.mark.benchmark

SIZES = [5, 25, 50]


@pytest.mark.parametrize("versions", SIZES)
def test_plan_chain(benchmark, versions: int) -> None:
    manager = build_chain(versions)
    runner = manager.runner()
    data = payload()
    plan = benchmark(
        runner.plan,
        data,
        "latest",
        container=None,
        max_depth=-1,
    )
    assert len(plan.path.entries) == 1


@pytest.mark.parametrize("versions", SIZES)
def test_execute_chain(benchmark, versions: int) -> None:
    manager = build_chain(versions)
    runner = manager.runner()
    data = payload()
    result = benchmark(runner.run, data, "latest")
    assert result["version"] == f"{versions - 1}.0.0"


@pytest.mark.parametrize("versions", SIZES)
def test_propose_migration(benchmark, versions: int) -> None:
    manager = build_chain(versions)
    source = manager.get("User", "0.0.0")
    target = manager.get("User", f"{versions - 1}.0.0")
    proposal = benchmark(manager.engine.propose_migration, source, target)
    assert proposal.spec["from"] == "0.0.0"


@pytest.mark.parametrize("versions", SIZES)
def test_export_jgf(benchmark, versions: int) -> None:
    manager = build_chain(versions)
    exporter = JgfExporter(default_content_hasher())
    graph = benchmark(exporter.export_graph, manager.registry)
    assert len(graph.nodes) == versions
