from __future__ import annotations

import inspect
import json
import math
import statistics
import timeit
from pathlib import Path
from typing import Annotated, Any

import typer

from .._helpers import load_json_file, write_json_file
from ..config import ConfigError, resolve_manager
from ._shared import ManagerOption, dump_json


def measure(
    execute: Any,
    *,
    iterations: int,
    warmup: int,
) -> list[float]:
    """Run calibrated in-process timings and return seconds per call."""
    for _ in range(warmup):
        execute()
    timer = timeit.Timer(execute)
    loops, _ = timer.autorange()
    return [total / loops for total in timer.repeat(iterations, loops)]


def _percentile(samples: list[float], percentile: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    index = max(
        0, min(len(ordered) - 1, math.ceil(percentile / 100 * len(ordered)) - 1)
    )
    return ordered[index]


def stats(samples: list[float]) -> dict[str, float | int]:
    """Convert timing samples into millisecond report metrics."""
    count = len(samples)
    mean = statistics.mean(samples)
    stdev = statistics.stdev(samples) if count > 1 else 0.0
    return {
        "count": count,
        "min_ms": min(samples) * 1000,
        "max_ms": max(samples) * 1000,
        "mean_ms": mean * 1000,
        "median_ms": statistics.median(samples) * 1000,
        "stdev_ms": stdev * 1000,
        "p95_ms": _percentile(samples, 95) * 1000,
        "p99_ms": _percentile(samples, 99) * 1000,
        "throughput_per_second": 1 / mean if mean else 0.0,
    }


def benchmark(
    manager: ManagerOption,
    payload: Annotated[Path, typer.Option("--payload", "-p", help="Payload JSON file")],
    target: Annotated[
        str, typer.Option("--target", "-t", help="Target policy/version")
    ] = "latest",
    iterations: Annotated[
        int,
        typer.Option("--iterations", "-n", min=1, help="Timed samples"),
    ] = 20,
    warmup: Annotated[int, typer.Option("--warmup", min=0, help="Warmup calls")] = 3,
    mode: Annotated[
        str, typer.Option("--mode", help="Benchmark mode: run or plan")
    ] = "run",
    context: Annotated[
        str | None, typer.Option("--context", help="Context JSON object")
    ] = None,
    context_file: Annotated[
        Path | None, typer.Option("--context-file", help="Context JSON file")
    ] = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write benchmark JSON")
    ] = None,
    baseline: Annotated[
        Path | None, typer.Option("--baseline", help="Compare against baseline JSON")
    ] = None,
    max_regression: Annotated[
        float,
        typer.Option("--max-regression", help="Maximum allowed regression percent"),
    ] = 20.0,
    format: Annotated[
        str, typer.Option("--format", help="Output format: text or json")
    ] = "text",
) -> None:
    """Measure payload planning or migration latency for CI budgets."""
    if mode not in {"run", "plan"}:
        typer.secho("--mode must be 'run' or 'plan'", fg=typer.colors.RED)
        raise typer.Exit(2)
    if max_regression < 0:
        typer.secho("--max-regression must be >= 0", fg=typer.colors.RED)
        raise typer.Exit(2)
    if format not in {"text", "json"}:
        typer.secho("--format must be 'text' or 'json'", fg=typer.colors.RED)
        raise typer.Exit(2)

    try:
        runtime_context = None
        if context_file is not None:
            runtime_context = load_json_file(context_file)
        elif context is not None:
            runtime_context = json.loads(context)

        manager_instance = resolve_manager(manager)
        data = load_json_file(payload)
        runner = manager_instance.runner()

        def execute() -> Any:
            if mode == "plan":
                return runner.plan(
                    data,
                    target,
                    container=None,
                    max_depth=-1,
                )
            result = runner.run(
                data,
                target,
                container=None,
                max_depth=-1,
                context=runtime_context,
            )
            if inspect.isawaitable(result):
                raise RuntimeError(
                    "benchmark command requires a sync backend; "
                    "use a sync manager runner"
                )
            return result

        samples = measure(
            execute,
            iterations=iterations,
            warmup=warmup,
        )
        metrics = stats(samples)
        report: dict[str, Any] = {
            "manager": manager,
            "target": target,
            "mode": mode,
            "iterations": iterations,
            "warmup": warmup,
            "metrics": metrics,
        }
        regressions: dict[str, float] = {}
        if baseline is not None:
            baseline_report = json.loads(baseline.read_text())
            baseline_metrics = baseline_report.get("metrics", baseline_report)
            for key in ("mean_ms", "p95_ms"):
                current = float(metrics[key])
                previous = float(baseline_metrics.get(key, 0.0))
                if previous > 0:
                    regressions[key] = ((current - previous) / previous) * 100
            report["baseline"] = {
                key: baseline_metrics.get(key) for key in ("mean_ms", "p95_ms")
            }
            report["regression_percent"] = regressions

        if output is not None:
            write_json_file(output, report)
        if format == "json":
            dump_json(report)
        else:
            typer.secho(
                f"Benchmark {mode}: {metrics['mean_ms']:.3f} ms mean, "
                f"{metrics['p95_ms']:.3f} ms p95",
                bold=True,
            )
            typer.echo(
                f"  iterations={iterations} warmup={warmup} "
                f"throughput={metrics['throughput_per_second']:.1f}/s"
            )

        if regressions and any(
            value > max_regression for value in regressions.values()
        ):
            typer.secho(
                f"Performance regression exceeds {max_regression:.1f}%",
                fg=typer.colors.RED,
            )
            raise typer.Exit(3)
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1) from exc
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1) from exc
    except typer.Exit:
        raise
    except Exception as exc:
        typer.secho(f"Benchmark failed: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc


__all__ = ["benchmark"]
