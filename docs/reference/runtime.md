# Runtime & Execution

A runtime is a `Runner` bound to one manager graph, adapter, backend, middleware
chain, and execution environment.

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

Pass `container=` to materialize and validate the result against a container
model:

```python
result = manager.runner().run(payload, "latest", container=UserEnvelope)
```

## Async

Use `AsyncBackend` to run coroutine migrations natively and sync migrations in
worker threads:

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

The backend determines whether `run()` is sync or awaitable. There is no
implicit event-loop creation.

## Backends

```python
from pyverge.execution import AsyncBackend, ProcessBackend, ThreadedBackend
```

- `ThreadedBackend(max_workers=0)` — default; sequential above 1 worker.
- `AsyncBackend(...)` — native coroutine execution with threaded sync fallback.
- `ProcessBackend(...)` — process-isolated execution for CPU or isolation needs.

## Runtime context

`MigrationContext` is a read-only view over the supplied mapping, not a copy.
The same instance reaches every step.

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

JSON Patch intentionally does not read context. JSONata reads context as
JSONata variables; callables receive the `MigrationContext` directly.

## Hooks

```python
from pyverge.execution import MigrationHook

class AuditHook(MigrationHook):
    def after_migrate(self, name, from_version, to_version, original, migrated):
        ...
```

Async execution awaits async hook overrides (`abefore_migrate`,
`aafter_migrate`, `aon_error`). If only the sync hook exists, it runs in a worker
thread via `asyncio.to_thread`, so it cannot block the event loop.

## Middleware

`manager.runner(middleware=(...))` accepts backend middleware for retry,
idempotency, transactions, audit, OpenTelemetry, and OpenLineage. Middleware
wraps the backend execution seam, not individual migrations.

See [Execution Flow](../explanation/execution-flow.md) for graph discovery and ordering, and
[Migration Formats](migration-formats.md) for authoring choices.
