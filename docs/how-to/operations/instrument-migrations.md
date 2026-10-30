# Instrument migrations with hooks

Migrations are observable. Hooks are read-only observers that run before,
after, or on error for each migration step — for logging, metrics, auditing, or
distributed tracing.

## Prerequisites

- A registered migration edge.
- A hook implementing the desired callbacks.

## Hook contract

Hooks receive the step name, `NodeId` endpoints, migration descriptor, and a
backend-provided `HookState`:

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
        print(
            f"migrating {migration.strategy if migration else name} "
            f"{from_version} -> {to_version}"
        )

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

`state` is not global and should not be stored on the hook instance. The
execution backend creates one `ContextVar` per run and adapts it per async task
or thread. Store per-step state in it by hook instance key when needed.

Register a hook on a specific migration edge:

```python
from pyverge.core import ManagerMigrationKey

manager.add_hook(
    ManagerMigrationKey("User", "1.0.0", "2.0.0"),
    AuditHook(),
)
```

An instance hook applies only to that manager instance. Register on the manager
class before instantiating if every instance should inherit the hook.

### Async hooks

Define async callbacks directly on the hook. The async backend awaits them:

```python
class AsyncAuditHook(MigrationHook):
    async def before_migrate(
        self,
        name,
        from_version,
        to_version,
        data,
        *,
        migration=None,
        state,
    ):
        await audit_write(migration, from_version, to_version)
```

There are no separate `abefore_migrate` / `aafter_migrate` methods. The sync
backend rejects awaitable hook results with `AsyncExecutionRequired`.

### OpenTelemetry

`OTELHook` creates a span per migration step. Wire it to your tracer provider:

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, OTLPSpanExporter

from pyverge.core import ManagerMigrationKey
from pyverge.execution import OTELHook

provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)

hook = OTELHook(tracer=trace.get_tracer("converge"), service="converge")
manager.add_hook(ManagerMigrationKey("User", "1.0.0", "2.0.0"), hook)
```

Each step emits `<service>.migrate` with:

```text
migration.name
migration.namespace
migration.kind
migration.source
migration.target
migration.strategy       # when available
migration.identity       # when available
migration.duration_seconds
```

### OpenLineage

`OpenLineageHook` emits edge-level START/COMPLETE/FAIL events. Use
`OpenLineageMiddleware` when you also want run-level lineage and namespace
validation:

```python
from pyverge.execution import OpenLineageHook
from pyverge.execution.middleware import OpenLineageMiddleware

middleware = OpenLineageMiddleware(
    client=client,
    namespace="com.acme.orders",
    producer="orders-service",
)
hook = OpenLineageHook(
    client=client,
    namespace="com.acme.orders",
    producer="orders-service",
)
```

The middleware validates that the OpenLineage namespace matches the graph
namespace when the graph has one. Dataset names use namespaced `NodeId` values;
job names identify the edge:

```text
migration.User.1.0.0->2.0.0
```

## Verify

```python
manager.attach_hooks([AuditHook()])
result = manager.runner().run(payload, "latest")
```

## Troubleshooting

- Hook not called: it is attached to a different edge or manager graph.
- Async hook not awaited: use `AsyncBackend`.
- `TypeError` about `state`: the hook implements an outdated callback
  signature. Add the keyword-only `state` parameter.
- OpenLineage namespace error: align the configured namespace with the graph
  namespace, or remove the graph namespace.

## See also

- [Test migrations](test-migrations.md)
- [Runtime reference](../../reference/runtime.md)
- [Run payloads](../runtime/run-payloads.md)
