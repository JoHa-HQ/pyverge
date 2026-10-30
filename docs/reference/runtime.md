# Runtime reference

A runtime is a `Runner` bound to one immutable manager graph snapshot, adapter,
backend, middleware chain, and execution environment.

Planning is graph-side: `PayloadWalker` discovers entries, and `PathFinder`
compiles target policy, resolves migration paths, applies policy, and checks
that every selected path is fully hydrated and bound before execution.

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
    def after_migrate(
        self,
        name,
        from_version,
        to_version,
        original,
        migrated,
        *,
        migration=None,
        state,
    ):
        ...
```

`from_version` and `to_version` are `NodeId` values. `migration` is the
`MigrationDescriptor` (`strategy`, `identity`) when available. `state` is a
backend-provided `ContextVar`; do not store per-step state on the hook instance.

There are no separate `abefore_migrate` / `aafter_migrate` methods. An async hook
is a `before_migrate` / `after_migrate` / `on_error` method declared with
`async def`; the async backend awaits it. The sync backend rejects awaitable
hook results.

## Middleware

`manager.runner(middleware=(...))` accepts backend middleware for retry,
idempotency, transactions, audit, OpenTelemetry, and OpenLineage. Middleware
wraps the backend execution seam, not individual migrations.

`OpenLineageMiddleware` validates the configured OpenLineage namespace against
the graph namespace when the graph has one. Datasets use namespaced `NodeId`
values; run events identify the complete execution while edge-level hooks emit
per-migration events.

See [Run payloads](../how-to/runtime/run-payloads.md) for examples and
[Execution flow](../explanation/execution-flow.md) for ordering.
