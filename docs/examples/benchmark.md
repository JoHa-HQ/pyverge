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

## Memory profiling with memray

Use memray when latency is acceptable but allocation growth is not.
Install it first:

<!--pytest.mark.skip-->

```bash
pip install memray
```

Profile the runtime execution seam with middleware. Each run writes one capture
file named by its `run_id`:

<!--pytest.mark.skip-->

```python
import sys
from pathlib import Path
from typing import Any

import memray

from demo_manager import UserManager


class MemrayMiddleware:
    def __init__(self, output_dir: str | Path) -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def wrap(self, inner: Any) -> Any:
        return _MemrayRun(inner, self._output_dir)


class _MemrayRun:
    def __init__(self, inner: Any, output_dir: Path) -> None:
        self._inner = inner
        self._output_dir = output_dir

    def execute(self, plan: Any, payload: Any, run: Any, adapter: Any) -> Any:
        tracker = memray.Tracker(self._output_dir / f"{run.run_id}.bin")
        tracker.__enter__()
        try:
            result = self._inner.execute(plan, payload, run, adapter)
        except BaseException:
            tracker.__exit__(*sys.exc_info())
            raise
        if hasattr(result, "__await__"):
            return self._await(result, tracker)
        tracker.__exit__(None, None, None)
        return result

    async def _await(self, result: Any, tracker: memray.Tracker) -> Any:
        try:
            value = await result
        except BaseException:
            tracker.__exit__(*sys.exc_info())
            raise
        tracker.__exit__(None, None, None)
        return value


manager = UserManager()
runner = manager.runner(middleware=(MemrayMiddleware("memray-runs"),))
payload = {
    "kind": "User",
    "version": "1.0.0",
    "name": "Alice",
    "email": "alice@example.com",
}

runner.run(payload, "latest")
```

Inspect the capture:

<!--pytest.mark.skip-->

```bash
RUN_FILE=memray-runs/<run_id>.bin
memray stats "$RUN_FILE"
memray tree "$RUN_FILE"
memray flamegraph "$RUN_FILE"
memray table "$RUN_FILE"
```

`memray stats` summarizes total allocations. `memray tree` and
`memray flamegraph` show allocation hotspots. `memray table` lists every
captured allocation record.

Memray supports Linux and macOS.
