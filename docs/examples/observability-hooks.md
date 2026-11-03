# Observe migrations with telemetry

Both examples are executed in CI. Telemetry adapters consume typed run and step
events from the runtime; choose the integration that matches your telemetry or
lineage backend.

## OpenTelemetry

```python
import semver
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import BaseModel

from pyverge import Manager
from pyverge.runtime import OtelAdapter
from pyverge.schemas import ModelCodec, PydanticModelAdapter

UserManager = Manager[semver.Version].configure(PydanticModelAdapter(codec=ModelCodec(namespace="default", version_property="version", kind_property="kind")))


@UserManager.model()
class UserV1(BaseModel):
    kind: str = "User"
    version: str = "1.0.0"
    name: str


@UserManager.model()
class UserV2(BaseModel):
    kind: str = "User"
    version: str = "2.0.0"
    name: str
    age: int = 0


@UserManager.migration("User", "1.0.0", "2.0.0", migration_id="docs.otel.v1_v2")
def add_age(data: dict, context=None) -> dict:
    return {**data, "age": 0}


exporter = InMemorySpanExporter()
provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(exporter))
manager = UserManager()
result = manager.runtime(
    telemetry=(OtelAdapter(tracer=provider.get_tracer("docs"), service="docs"),),
).runner.run(
    {"kind": "User", "version": "1.0.0", "name": "Alice"},
    "latest",
)

assert result["version"] == "2.0.0"
spans = {span.name: span for span in exporter.get_finished_spans()}
assert set(spans) == {"docs.run", "docs.migrate"}
step_span = spans["docs.migrate"]
assert step_span.attributes["migration.kind"] == "User"
assert step_span.attributes["migration.strategy"] == "callable"
assert step_span.attributes["migration.identity"] == "docs.otel.v1_v2"
```

## OpenLineage

```python
import semver
from pydantic import BaseModel

from pyverge import Manager
from pyverge.runtime import OpenLineageAdapter
from pyverge.schemas import ModelCodec, PydanticModelAdapter

LineageUserManager = Manager[semver.Version].configure(PydanticModelAdapter(codec=ModelCodec(namespace="default", version_property="version", kind_property="kind")))


@LineageUserManager.model()
class LineageUserV1(BaseModel):
    kind: str = "User"
    version: str = "1.0.0"
    name: str


@LineageUserManager.model()
class LineageUserV2(BaseModel):
    kind: str = "User"
    version: str = "2.0.0"
    name: str
    age: int = 0


@LineageUserManager.migration(
    "User",
    "1.0.0",
    "2.0.0",
    migration_id="docs.openlineage.v1_v2",
)
def add_age(data: dict, context=None) -> dict:
    return {**data, "age": 0}


class LineageClient:
    def __init__(self) -> None:
        self.events = []

    def emit(self, event) -> None:
        self.events.append(event)


lineage = LineageClient()
lineage_manager = LineageUserManager()
lineage_result = lineage_manager.runtime(
    telemetry=(
        OpenLineageAdapter(
            client=lineage,
            namespace="default",
            producer="docs-example",
        ),
    ),
).runner.run(
    {"kind": "User", "version": "1.0.0", "name": "Alice"},
    "latest",
)

assert lineage_result["version"] == "2.0.0"
assert [event.eventType.value for event in lineage.events] == [
    "START",
    "START",
    "COMPLETE",
    "COMPLETE",
]
assert lineage.events[0].job.name == "migration.run"
assert lineage.events[1].job.name == "migration.User.1.0.0->2.0.0"
```
