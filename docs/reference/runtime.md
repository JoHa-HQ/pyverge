# Runtime reference

A runtime is a `Runner` bound to one manager graph, adapter, backend, middleware
chain, and execution environment.

## Runner

```python
manager.runner(
    *,
    runtime=None,
    backend=None,
    middleware=(),
    environment=None,
    direction="any",
    on_direction_violation="skip",
    on_missing_path="raise",
    depth_limit=-1,
    on_depth_violation="skip",
    validation_mode="lax",
)
```

`Runner.run`:

```python
runner.run(
    payload,
    target,
    *,
    container=None,
    max_depth=-1,
    context=None,
    run_id=None,
)
```

## Backends

| Backend | Behavior |
| --- | --- |
| `ThreadedBackend(max_workers=0)` | default; sequential, or thread-pool execution when workers > 0 |
| `AsyncBackend(backend, backend_options, max_workers)` | native coroutine execution with threaded sync fallback |
| `ProcessBackend(max_workers)` | process-isolated execution |

The backend determines whether `run()` returns a result or an awaitable.

## Hooks

`MigrationHook` callbacks observe each migration step:

```python
class AuditHook(MigrationHook):
    def after_migrate(self, name, from_version, to_version, original, migrated):
        ...
```

Async execution awaits async hook overrides (`abefore_migrate`,
`aafter_migrate`, `aon_error`). Sync hooks run in a worker thread when needed.

## Middleware

`manager.runner(middleware=(...))` accepts backend middleware for retry,
idempotency, transactions, audit, OpenTelemetry, and OpenLineage. Middleware
wraps the backend execution seam, not individual migrations.

See [Run payloads](../how-to/run-payloads.md) for examples and
[Execution flow](../explanation/execution-flow.md) for ordering.
