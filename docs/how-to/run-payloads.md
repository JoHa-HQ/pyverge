# Run payloads

Task examples for sync, async, process-isolated, and context-aware execution.

## Sync

```python
runner = manager.runner()
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
result = manager.runner().run(payload, "latest", container=UserEnvelope)
```

## Async

```python
from pyverge.execution import AsyncBackend

runner = manager.runner(
    runtime=AsyncBackend(
        backend="asyncio",
        backend_options={},
        max_workers=4,
    )
)
result = await runner.run(payload, "latest")
```

No implicit event loop is created. Use `AsyncBackend` when migrations are async
or when async concurrency is desired.

## Process isolation

```python
from pyverge.execution import ProcessBackend

backend = ProcessBackend(max_workers=2)
try:
    result = manager.runner(runtime=backend).run(payload, "latest")
finally:
    backend.close()
```

## Runtime context

```python
result = manager.runner().run(
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

## See also

- [Runtime reference](../reference/runtime.md)
- [Telemetry and hooks](telemetry.md)
- [Target policy](../reference/target-policy.md)
