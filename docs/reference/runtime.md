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

`MigrationHook` callbacks observe each migration step.

```python
from typing import Any

from pyverge.core.types import HookState
from pyverge.execution import MigrationHook
from pyverge.versioning import MigrationDescriptor, NodeId


class AuditHook(MigrationHook):
    def before_migrate(
        self,
        name: str,
        from_version: NodeId,
        to_version: NodeId,
        data: dict[str, Any],
        *,
        migration: MigrationDescriptor | None = None,
        state: HookState,
    ) -> None:
        print(f"migrating {from_version} -> {to_version}")

    def after_migrate(
        self,
        name: str,
        from_version: NodeId,
        to_version: NodeId,
        original_data: dict[str, Any],
        migrated_data: dict[str, Any],
        *,
        migration: MigrationDescriptor | None = None,
        state: HookState,
    ) -> None:
        print(f"migrated {from_version} -> {to_version}")

    def on_error(
        self,
        name: str,
        from_version: NodeId,
        to_version: NodeId,
        data: dict[str, Any],
        error: Exception,
        *,
        migration: MigrationDescriptor | None = None,
        state: HookState,
    ) -> None:
        print(f"failed {from_version} -> {to_version}: {error}")
```

`from_version` and `to_version` are `NodeId` values. `migration` is the
`MigrationDescriptor` (`strategy`, `identity`) when available. `state` is a
backend-provided `ContextVar`; do not store per-step state on the hook instance.
Store it in `state` by hook instance key when needed.

Register a hook on a specific edge:

```python
from pyverge.types import ManagerMigrationKey

manager.add_hook(
    ManagerMigrationKey("User", "1.0.0", "2.0.0"),
    AuditHook(),
)
```

An instance hook applies only to that manager instance. Register on the manager
class before instantiating if every instance should inherit the hook.

There are no separate `abefore_migrate` / `aafter_migrate` methods. An async hook
is a `before_migrate` / `after_migrate` / `on_error` method declared with
`async def`; the async backend awaits it. The sync backend rejects awaitable
hook results with `AsyncExecutionRequired`.

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
