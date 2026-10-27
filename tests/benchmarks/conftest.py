from __future__ import annotations

from pathlib import Path

from tests.benchmarks.report import write_reports


def pytest_sessionstart(session) -> None:
    Path("reports").mkdir(exist_ok=True)


def pytest_benchmark_update_json(config, benchmarks, output_json) -> None:
    if "benchmark" not in config.getoption("markexpr", default=""):
        return
    json_path = config.getoption("benchmark_json", default=None)
    if not json_path:
        return
    write_reports(Path(json_path), output_json)
