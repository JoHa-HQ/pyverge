# Instrument migrations with hooks and telemetry

Migrations are observable in two ways. `MigrationHook` callbacks run before,
after, or on error for custom behavior. Telemetry adapters consume typed runtime
lifecycle events for tracing and lineage.

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

`OtelAdapter` creates one run span and one span per migration step. Wire it to
your tracer provider and pass it to `manager.runtime(telemetry=...)`:

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, OTLPSpanExporter

from pyverge.runtime import OtelAdapter

provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)

adapter = OtelAdapter(tracer=trace.get_tracer("converge"), service="converge")
runner = manager.runtime(telemetry=(adapter,)).runner
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
migration.discriminator
migration.duration_seconds
```

### Configure OpenLineage

`OpenLineageAdapter` emits both run-level and step-level START/COMPLETE/FAIL
events:

```python
from pyverge.runtime import OpenLineageAdapter

adapter = OpenLineageAdapter(
    client=client,
    namespace="com.acme.orders",
    producer="orders-service",
)
runner = manager.runtime(telemetry=(adapter,)).runner
```

The adapter checks that the OpenLineage namespace matches the graph namespace
when the graph has one. Dataset names use namespaced `NodeId` values; job names
identify the edge:

```text
migration.User.1.0.0->2.0.0
```

Step events carry data metadata, not payload values:

- dataset version facets for the source and target versions
- schema facets built from the source and target model fields
- job type and migration tags for name, strategy, identity, and discriminator
- processing engine and parent-run facets linking each step to its run
- an error facet on failed steps

Payload content is never emitted, so lineage stays free of application data and
PII.

Telemetry is best-effort and isolated: an adapter failure is logged, does not
fail the migration, and does not prevent other adapters from receiving the
event.

## Verify

```python
manager.attach_hooks([AuditHook()])
result = manager.runtime(
    telemetry=(OtelAdapter(tracer=trace.get_tracer("converge")),),
).runner.run(payload, "latest")
```

## Troubleshooting

- Hook not called: it is attached to a different edge or manager graph.
- Async hook not awaited: use `AsyncBackend`.
- `TypeError` about `state`: the hook implements an outdated callback
  signature. Add the keyword-only `state` parameter.
- OpenLineage namespace mismatch: align the configured namespace with the graph
  namespace, or remove the graph namespace. The mismatch is logged and the
  adapter emits nothing because telemetry is best-effort.

## See also

- [Test migrations](test-migrations.md)
- [Runtime reference → Hooks](../../reference/runtime.md#hooks)
- [Run payloads](../runtime/run-payloads.md)
