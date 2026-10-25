# Benchmark adapters

pyverge has correctness tests; this page covers measuring **cost** at the adapter
layer — what a host adapter adds per message or call, and at startup — without
reaching into engine internals.

The harness lives in [`benchmarks/`https://github.com/JoHa-HQ/pyverge/tree/main/benchmarks;
its README is the reference. This page is the overview.

## Prerequisites

- A working adapter test environment.
- `pytest-benchmark`.
- Generated payloads for the registered models.

## Steps

See [benchmarking model](../../explanation/benchmarking.md) for what is measured and how baselines work.

### Running

```bash
uv run pytest benchmarks/ -o addopts="--benchmark-only"
```

The `-o addopts=...` override drops the suite's coverage and doctest flags, which
would otherwise perturb and fail a benchmark run. `benchmarks/` is out of the
default `testpaths`, so a plain `pytest` never runs benchmarks.

## Verify

```bash
uv run pytest benchmarks/ -o addopts="--benchmark-only"
```

## Troubleshooting

- Benchmark errors from payload validation mean generated data is stale.
- Missing baseline: verify the paired baseline benchmark exists.

## See also

- [Testing](test-migrations.md) — the correctness suite and its guards.
- [Telemetry & Hooks](instrument-migrations.md) — per-migration spans, useful for latency.
