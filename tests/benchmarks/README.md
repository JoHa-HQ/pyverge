# Benchmarks

Two benchmark families:

- `adapters/` — adapter overhead and source traversal.
- `migrations/` — schema migration graph complexity.

Benchmarks live under `tests/` but use a dedicated profile and marker.

## Run

Default test run excludes `benchmark`:

```bash
pytest
```

Benchmark profile:

```bash
pytest -c pytest-bench.toml
```

Equivalent explicit command:

```bash
pytest tests/benchmarks -m benchmark \
  -o addopts="--benchmark-only --benchmark-json=reports/benchmarks.json"
```

Subsets:

```bash
pytest tests/benchmarks/adapters -c pytest-bench.toml
pytest tests/benchmarks/migrations -c pytest-bench.toml
```

## Rendered results

The benchmark profile writes:

```text
reports/benchmarks.json
reports/benchmarks.md
reports/benchmarks.html
```

Rendering runs through the `pytest_benchmark_update_json` hook and only when the
`benchmark` marker is selected.

## Migration graph benchmarks

`migrations/bench_graph.py` parametrizes linear chains by version count and
measures planning, execution, migration proposal, and JGF export.

## Reading results

Adapter suites pair with a baseline (plain framework, no pyverge). The delta
isolates adapter overhead from framework overhead.
