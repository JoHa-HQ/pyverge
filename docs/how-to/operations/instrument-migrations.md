# Instrument migrations with hooks

Migrations are observable. Hooks are read-only observers that run before,
after, or on error for each migration step — for logging, metrics, auditing, or
distributed tracing.

## Prerequisites

- A registered migration edge.
- A hook implementing the desired callbacks.

## Steps

## Writing a hook

Subclass `MigrationHook` and override only the callbacks you need:

```python
from pyverge.execution import MigrationHook


class AuditHook(MigrationHook):
    def before_migrate(self, name, from_version, to_version, data):
        print(f"migrating {name} {from_version} -> {to_version}")

    def after_migrate(self, name, from_version, to_version, original_data, migrated_data):
        print(f"migrated {name} {from_version} -> {to_version}")

    def on_error(self, name, from_version, to_version, data, error):
        print(f"failed {name} {from_version} -> {to_version}: {error}")
```

Register a hook on a specific migration edge:

```python
from pyverge.core import ManagerMigrationKey

manager.add_hook(ManagerMigrationKey("User", "1.0.0", "2.0.0"), AuditHook())
```

An instance hook applies only to that manager instance. Register on the manager
class before instantiating if every instance should inherit the hook.

### Async hooks

Async executors use async overrides when present:

```python
class AsyncAuditHook(MigrationHook):
    async def abefore_migrate(self, name, from_version, to_version, data):
        await audit_write(name, from_version, to_version, data)
```

If only the sync methods exist, the async executor runs them in a worker thread
via `asyncio.to_thread`; sync hooks do not block the event loop.

### OpenTelemetry

`OTELHook` (in the adapters layer) creates a span per migration with duration,
status, and exception recording. Wire it to your tracer provider:

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, OTLPSpanExporter

from pyverge.execution import OTELHook
from pyverge.core import ManagerMigrationKey

provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)

hook = OTELHook(tracer=trace.get_tracer("converge"), service="converge")
manager.add_hook(ManagerMigrationKey("User", "1.0.0", "2.0.0"), hook)
```

Each migration step emits a span named `<service>.migrate` with attributes for
the kind and the from/to versions, plus duration and status on completion.

## Verify

```python
manager.attach_hooks([MyHook()])
```

## Troubleshooting

- Hook not called: it is attached to a different edge or manager graph.
- Async hook not awaited: use `AsyncBackend`.

## See also

- [Test migrations](test-migrations.md)
- [Benchmark adapters](benchmark-adapters.md)
- [Run payloads](../runtime/run-payloads.md)
