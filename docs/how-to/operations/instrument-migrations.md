# Instrument migrations with hooks

Migrations are observable. Hooks are read-only observers that run before,
after, or on error for each migration step — for logging, metrics, auditing, or
distributed tracing.

## Prerequisites

- A registered migration edge.
- A hook implementing the desired callbacks.

## Steps

### Implement the callbacks

Implement `before_migrate`, `after_migrate`, and `on_error` on a
`MigrationHook`. The full callback contract, the `state` lifecycle, the worked
`AuditHook`, and async-hook rules live in
[Runtime reference → Hooks](../../reference/runtime.md#hooks).

### Register the hook

```python
from pyverge.types import ManagerMigrationKey

manager.add_hook(
    ManagerMigrationKey("User", "1.0.0", "2.0.0"),
    AuditHook(),
)
```

An instance hook applies only to that manager instance. Register on the manager
class before instantiating if every instance should inherit the hook.

### Configure OpenTelemetry

`OTELHook` creates a span per migration step. Wire it to your tracer provider:

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, OTLPSpanExporter

from pyverge.types import ManagerMigrationKey
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

### Configure OpenLineage

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
- [Runtime reference → Hooks](../../reference/runtime.md#hooks)
- [Run payloads](../runtime/run-payloads.md)
