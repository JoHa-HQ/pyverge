# Run payloads

Task examples for sync, async, process-isolated, and context-aware execution.

## Prerequisites

- A configured runtime manager.
- A target policy.
- A backend matching sync, async, or process execution needs.

## Steps

### Before execution

Planning validates the complete selected path against the graph snapshot:

- every selected node must be hydrated;
- every selected edge must have an executable migration binding;
- the graph namespace must match the manager namespace.

Key-only nodes and unbound edges are valid graph content, but they forbid
execution until completed.

### Sync

```python
runner = manager.runtime().runner
result = runner.run(payload, "latest")
```

`Runner.run()` defaults:

```text
container=None
max_depth=-1
context=None
```

Validate the target schema when required:

```python
result = manager.runtime().runner.run(
    payload,
    "latest",
    validate_target=True,
)
```

### Cache plans and control copying

```python
runner = manager.runtime(
    plan_cache_size=128,
    copy="none",
).runner
```

```text
plan_cache_size=0    disable plan caching
plan_cache_size=-1   unbounded cache
plan_cache_size=N    bounded LRU
```

```text
copy="deep"     safe default
copy="shallow"  top-level copy only
copy="none"     caller-owned payload, mutations are visible
```

Plan caching keys on the target policy and entry signature, never payload
values.

### Batch payloads

```python
results = runner.run_many(
    payloads,
    "latest",
    context={"tenant_id": "tenant_99"},
)
```

Each payload gets its own run ID, run context, transaction scope, and telemetry
events. The plan cache is reused across the batch.

### Async

```python
from pyverge.runtime import AsyncBackend

runner = manager.runtime(
    runtime=AsyncBackend(
        backend="asyncio",
        backend_options={},
        max_workers=4,
    )
).runner
result = await runner.run(payload, "latest")
```

No implicit event loop is created. Use `AsyncBackend` when migrations are async
or when async concurrency is desired.

### Process isolation

```python
from pyverge.runtime import ProcessBackend

backend = ProcessBackend(max_workers=2)
try:
    result = manager.runtime(runtime=backend).runner.run(payload, "latest")
finally:
    backend.close()
```

Use `ProcessBackend` for CLI and offline batch jobs. In Celery, FastStream, or
other frameworks that already own worker processes, use one runtime per worker
with `ThreadedBackend` or `AsyncBackend` to avoid nested process pools.

### Runtime context

```python
result = manager.runtime().runner.run(
    payload,
    "latest",
    context={"tenant_id": "tenant_99", "rates": {"USD": 1.08}},
)
```

Migration callables receive context as an optional second argument:

```python
def migrate(data, context=None):
    data["tenant_id"] = context["tenant_id"]
    return data
```

JSON Patch does not read context. JSONata reads context as variables.

## Verify

```python
result = manager.runtime().runner.run(payload, "latest")
```

## Troubleshooting

- Awaitable result with sync backend: use `AsyncBackend`.
- Process failures: ensure migration callables and context are picklable.

## See also

- [Runtime reference](../../reference/runtime.md)
- [Telemetry and hooks](../operations/instrument-migrations.md)
- [Target policy](../../reference/target-policy.md)
