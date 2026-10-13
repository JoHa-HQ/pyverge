# Benchmarking pyverge adapters

pyverge has correctness tests; this page covers measuring **cost** at the adapter
layer — what a host adapter adds per message or call, and at startup — without
reaching into engine internals.

The harness lives in [`benchmarks/`](https://github.com/JoHa-HQ/pyverge/tree/main/benchmarks);
its README is the reference. This page is the overview.

## What is measured

Adapters only:

- **FastStream** — consume (`publish → decoder convergence → handler`), the in/out
  bridge, and startup reflection.

The migration engine is treated as a black box: no `manager.migrate`, registry,
or diff micro-benchmarks.

## Schema-rigorous payloads

Benchmarks never hand-write payloads. `benchmarks/synthesis.py` generates
instances from the registered models with Hypothesis
(`st.from_type(model)`), serializes them through the adapter's own `manager.dump`,
and validates each against its source version. A payload that fails validation
raises.

A guard (`tests/test_benchmark_synthesis.py`) runs with the normal suite: schema
drift fails the build instead of silently poisoning benchmarks.

## Baselines

Every adapter suite pairs with a plain-framework baseline (a FastStream subscriber
with no pyverge). The difference between the two isolates the adapter's cost from
the framework's, which is what you actually want to track over time.

## Running

```bash
uv run pytest benchmarks/ -o addopts="--benchmark-only"
```

The `-o addopts=...` override drops the suite's coverage and doctest flags, which
would otherwise perturb and fail a benchmark run. `benchmarks/` is out of the
default `testpaths`, so a plain `pytest` never runs benchmarks.

For sustained throughput, use the load script (`uv run python -m
benchmarks.load_faststream`) rather than pytest-benchmark, which is sync-only and
single-threaded.

## Profiling

Sampling (`py-spy`), deterministic (`cProfile`), and allocation (`memray`)
recipes are in the benchmarks README.

## See also

- [Testing](testing.md) — the correctness suite and its guards.
- [Telemetry & Hooks](telemetry.md) — per-migration spans, useful for latency.
