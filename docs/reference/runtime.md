# Runtime reference

A runtime owns one immutable manager graph snapshot, adapter, backend,
middleware chain, and execution environment. `Runtime.runner` is the bound
execution surface.

Planning is graph-side: `PayloadWalker` discovers entries, and `PathFinder`
compiles target policy, resolves migration paths, applies policy, and checks
that every selected path is fully hydrated and bound before execution.

## Runner

```python
runtime = manager.runtime(
    *,
    runtime=None,
    backend=None,
    middleware=(),
    telemetry=(),
    environment=None,
    direction="any",
    on_direction_violation="skip",
    on_missing_path="raise",
    depth_limit=-1,
    on_depth_violation="skip",
    validation_mode="lax",
    discriminator="default",
)
runner = runtime.runner
graph = runtime.graph
```

`Manager.runner(...)` remains as a deprecated shim.

`discriminator` selects the parallel edge used for every step. The default is
`"default"`; graph-level selection is:

```python
graph.edge_path(source, target, discriminator="canary")
```

Runtime-level selection is:

```python
manager.runtime(discriminator="canary").runner.run(payload, "latest")
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

| Backend | Strategy | Behavior |
| --- | --- | --- |
| `ThreadedBackend(max_workers=0)` | `ThreadedStrategy` | default; sequential, or thread-pool execution when workers > 0 |
| `AsyncBackend(backend, backend_options, max_workers)` | `AsyncStrategy` | native coroutine execution; sync callables run in the event loop |
| `ProcessBackend(max_workers)` | `ProcessStrategy` | process-isolated callable execution |

Backends own scheduling and callable invocation only. Entry payload read/write,
step contexts, version stamping, and hook scope lifecycles live in the
execution plan and step invoker, so every backend behaves the same way.

A strategy receives only the migration callable, the current value, and the
step context view. It does not read or write payload paths, run hooks, or build
step metadata:

```python
def invoke(func, data, context):
    return func(data, context)
```

The backend determines whether `run()` returns a result or an awaitable.

## Hooks

`MigrationHook` callbacks observe each migration step.

```python
from typing import Any

from pyverge.core.types import HookState
from pyverge.runtime import MigrationHook
from pyverge.runtime.context import StepContext


class AuditHook(MigrationHook):
    def before_migrate(
        self,
        step: StepContext,
        data: dict[str, Any],
        *,
        state: HookState,
    ) -> None:
        print(
            f"migrating {step.source} -> {step.target} "
            f"[{step.edge.discriminator}]"
        )

    def after_migrate(
        self,
        step: StepContext,
        original_data: dict[str, Any],
        migrated_data: dict[str, Any],
        *,
        state: HookState,
    ) -> None:
        print(f"migrated {step.source} -> {step.target}")

    def on_error(
        self,
        step: StepContext,
        data: dict[str, Any],
        error: Exception,
        *,
        state: HookState,
    ) -> None:
        print(f"failed {step.source} -> {step.target}: {error}")
```

`step` is the execution step context: `name`, source/target nodes, `edge`
(including `discriminator`), `migration` descriptor, payload `path`, and
`index`. It also exposes telemetry-ready `source_dataset` and `target_dataset`
views with namespace, kind, version, name, and field metadata. Hooks should use
those views instead of inspecting model descriptors. `state` is a
backend-provided `ContextVar`; do not store per-step state on the hook instance.
Store it in `state` by hook instance key when needed.

`before_migrate` may return a per-step context manager. Sync scopes implement
`HookScope` and are entered with `ExitStack`; async scopes implement
`AsyncHookScope` and are entered with `AsyncExitStack` by the async backend.
Resources are closed on success, error, or cancellation.

Hooks are for custom behavior. Telemetry uses lifecycle adapters instead, so
hooks no longer need to own run or step telemetry resources.

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

## Telemetry

`manager.runtime(telemetry=(...))` attaches lifecycle adapters. The runtime
emits six typed events:

```text
RunStarted
  StepStarted
  StepCompleted | StepFailed
RunCompleted | RunFailed
```

Run events carry the `RunContext` and `ExecutionPlan`; step events carry the
`StepContext`. Adapters implement one synchronous method:

```python
class TelemetryAdapter:
    def emit(self, event: TelemetryEvent) -> None: ...
```

Emission is best-effort and isolated. An adapter failure is logged, does not
fail the migration, and does not prevent other adapters from receiving the
event. Payload values are never emitted.

Bundled adapters:

```python
from pyverge.runtime import OpenLineageAdapter, OtelAdapter

runner = manager.runtime(
    telemetry=(
        OtelAdapter(tracer=trace.get_tracer("orders"), service="orders"),
        OpenLineageAdapter(
            client=lineage_client,
            namespace="com.acme.orders",
            producer="orders-service",
        ),
    )
).runner
```

`OpenLineageAdapter` emits run-level and step-level events with version, schema,
job, parent-run, and error facets. A namespace mismatch is logged and the
adapter emits nothing, because telemetry cannot fail the migration.

## Middleware

`manager.runtime(middleware=(...))` accepts control middleware for retry,
idempotency, transactions, and audit. Middleware wraps the backend execution
seam, not individual migrations.

See [Run payloads](../how-to/runtime/run-payloads.md) for examples and
[Execution flow](../explanation/execution-flow.md) for ordering.
