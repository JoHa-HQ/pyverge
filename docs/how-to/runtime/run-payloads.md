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

Materialize and validate a container result:

```python
result = manager.runtime().runner.run(payload, "latest", container=UserEnvelope)
```

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
