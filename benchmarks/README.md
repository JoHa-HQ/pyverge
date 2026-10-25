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
