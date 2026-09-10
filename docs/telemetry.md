# Telemetry & Hooks

Migrations are observable. Hooks are read-only observers that run before,
after, or on error for each migration step — for logging, metrics, auditing, or
distributed tracing.

## Writing a hook

Subclass `MigrationHook` and override only the callbacks you need:

```python
from pyverge.migration import MigrationHook


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
manager.add_hook(("User", "1.0.0", "2.0.0"), AuditHook())
```

## OpenTelemetry

`OTELHook` creates a span per migration with duration, status, and exception
recording. Wire it to your tracer provider:

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, OTLPSpanExporter

from pyverge.migration import OTELHook

provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)

hook = OTELHook(tracer=trace.get_tracer("converge"), service="converge")
manager.add_hook(("User", "1.0.0", "2.0.0"), hook)
```

Each migration step emits a span named `<service>.migrate` with attributes for
the kind and the from/to versions, plus duration and status on completion.
