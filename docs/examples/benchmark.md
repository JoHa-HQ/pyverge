# Benchmark latency

Benchmark payload execution or planning with `timeit` calibration:

<!--pytest.mark.skip-->

```bash
pyverge benchmark \
  --manager demo_manager:UserManager \
  --payload data.json \
  --iterations 20 \
  --warmup 3 \
  --format json
```

Write a baseline, then fail CI when mean or p95 latency regresses:

<!--pytest.mark.skip-->

```bash
pyverge benchmark \
  --manager demo_manager:UserManager \
  --payload data.json \
  --output target/benchmark.json

pyverge benchmark \
  --manager demo_manager:UserManager \
  --payload data.json \
  --baseline target/benchmark.json \
  --max-regression 20
```

The command exits `3` when the regression exceeds `--max-regression`.

## See also

- [Profile execution memory](../how-to/operations/profile-execution.md) — allocation
  profiling through a runner middleware.
- [Benchmark adapters](../how-to/operations/benchmark-adapters.md) — adapter cost
  and baselines.
