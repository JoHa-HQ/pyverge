# Profile execution memory

Use allocation profiling when latency is acceptable but memory growth is not.

## Prerequisites

- A working manager and runner.
- `memray` installed:

  ```bash
  pip install memray
  ```

## Steps

### Add a profiling middleware

The middleware wraps the runtime execution seam. Each run writes one capture
file named by its `run_id`:

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
```

### Run a payload

```python
manager = UserManager()
runner = manager.runtime(middleware=(MemrayMiddleware("memray-runs"),)).runner
payload = {
    "kind": "User",
    "version": "1.0.0",
    "name": "Alice",
    "email": "alice@example.com",
}

runner.run(payload, "latest")
```

### Inspect the capture

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

## Verify

```bash
ls memray-runs
```

Each converged run should produce one capture file.

## Troubleshooting

- **No capture file:** the middleware was not attached to the runner.
- **Profiling overhead is unacceptable:** keep the profiler out of latency
  benchmarks and out of production runners.
- **Platform support:** memray supports Linux and macOS.

## See also

- [Benchmark latency](../../examples/benchmark.md) — `pyverge benchmark` for
  latency thresholds.
- [Benchmark adapters](benchmark-adapters.md) — adapter cost and baselines.
- [Run payloads](../runtime/run-payloads.md) — runner and middleware usage.
