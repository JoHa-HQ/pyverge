# Runtime & Execution

The manager converges payloads through a prepared run, an execution backend,
and an execution strategy.

## Sync and async

```python
result = manager.migrate(payload, target="latest")
result = await manager.amigrate(payload, target="latest")
```

Execution policy comes from `MigrationSettings`:

```python
MigrationSettings(execution_mode="async", parallel_workers=4)
```

| Setting | Result |
| --- | --- |
| `parallel_workers=0` | sequential |
| `parallel_workers>0` | level-parallel, capped at CPU count |
| `execution_mode="sync"` | thread pool for parallel levels |
| `execution_mode="async"` | `asyncio.gather` |

Mode mismatches raise `AsyncExecutionRequired` or `SyncExecutionRequired`.
There is no implicit event-loop creation.

## Prepared runs

`manager.delegate` and `manager.prepare` build a `MigrationRun` without
executing it:

```python
run = manager.delegate(payload, container=UserEnvelope)

first = run.run(context={"tenant_id": "tenant_a"})
second = run.run(context={"tenant_id": "tenant_b"})
```

Context is supplied at execution time, so one run can be reused with different
bindings. Async runs use `await run.arun(context=...)`.

When `container=` is supplied, the run returns the typed container instance.
Engine-level runs stay payload-only (`materialize=False`).

## Runtime context

`MigrationContext` is a read-only view over the supplied mapping, not a copy.
The same instance reaches every step.

```python
result = manager.migrate(
    payload,
    context={"tenant_id": "tenant_99", "rates": {"USD": 1.08}},
)
```

Migration callables receive context as an optional second argument:

```python
def migrate(data, context=None):
    data["tenant_id"] = context["tenant_id"]
    return data
```

JSON Patch intentionally does not read context; use a callable.

## Hooks

```python
from pyverge.migration import MigrationHook

class AuditHook(MigrationHook):
    def after_migrate(self, name, from_version, to_version, original, migrated):
        ...
```

Async executors await async overrides (`abefore_migrate`, `aafter_migrate`,
`aon_error`). If only the sync hook exists, it runs in a worker thread via
`asyncio.to_thread`, so it cannot block the event loop.

## Backends and strategies

- `ExecutionPolicy` selects the strategy.
- `ExecutionBackend` runs entries; `LocalExecutionBackend` owns registry and
  adapter access.
- Strategies only iterate the graph and call the backend, so local and remote
  execution share the same seam.
- `ExecutionTransport` / `StepRequest` define the future FaaS contract
  (Lambda, Step Functions).

See [Execution Flow](execution-flow.md) for graph discovery and ordering, and
[Migration Formats](migration-formats.md) for authoring choices.
