# Adapter benchmarks

Payloads are synthesized from the registered models with Hypothesis and validated against their source version, so no benchmark measures a shape the adapter would reject.

## Run

Benchmarks are excluded from the default suite (`testpaths = ["tests"]`) and are collected as `bench_*.py`. Run them with the global coverage/doctest addopts
overridden:

```bash
# run
uv run pytest benchmarks/ -o addopts="--benchmark-only"

# save / compare against a baseline
uv run pytest benchmarks/ -o addopts="--benchmark-only --benchmark-autosave"
uv run pytest benchmarks/ -o addopts="--benchmark-only --benchmark-compare"
```

## Reading results

Each adapter suite pairs with a **baseline** (plain framework, no pyverge):
`test_consume_with_pyverge` vs `test_consume_baseline`. The delta isolates the
adapter from FastStream's own overhead.

## Load

```bash
uv run python -m benchmarks.load_faststream
```

## Profiling

```bash
uv run py-spy record -o profile.svg -- python -m benchmarks.load_faststream
uv run python -m cProfile -s cumtime benchmarks/load_faststream.py
uv run memray run benchmarks/load_faststream.py && memray flamegraph memray-*.bin
```
