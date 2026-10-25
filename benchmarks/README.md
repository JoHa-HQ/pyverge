# Benchmarks

Two benchmark families:

- `benchmarks/adapters/` — adapter overhead and source traversal.
- `benchmarks/migrations/` — schema migration graph complexity.

Adapter payloads are synthesized from registered models with Hypothesis and
validated against their source version.

## Run

Benchmarks are excluded from the default suite (`testpaths = ["tests"]`) and are collected as `bench_*.py`. Run them with the global coverage/doctest addopts
overridden:

```bash
# all benchmarks
uv run pytest benchmarks/ -o addopts="--benchmark-only"

# adapter only
uv run pytest benchmarks/adapters -o addopts="--benchmark-only"

# migration graph only
uv run pytest benchmarks/migrations -o addopts="--benchmark-only"

# save / compare against a baseline
uv run pytest benchmarks/ -o addopts="--benchmark-only --benchmark-autosave"
uv run pytest benchmarks/ -o addopts="--benchmark-only --benchmark-compare"
```

## Migration graph benchmarks

`benchmarks/migrations/bench_graph.py` parametrizes linear chains by version
count and measures:

- planning
- end-to-end execution
- migration proposal
- JGF export

## Reading results

Each adapter suite pairs with a **baseline** (plain framework, no pyverge):
`test_consume_with_pyverge` vs `test_consume_baseline`. The delta isolates the
adapter from FastStream's own overhead.
