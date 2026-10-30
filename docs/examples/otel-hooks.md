# OTel hooks

This page is executed in CI.

```python
import semver
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import BaseModel

from pyverge import Manager
from pyverge.execution import OTELHook
from pyverge.schemas import ModelCodec, PydanticModelAdapter

UserManager = Manager[semver.Version].configure(PydanticModelAdapter(codec=ModelCodec(namespace="", version_property="version", kind_property="kind")))


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
UserManager.attach_hooks(
    [OTELHook(tracer=provider.get_tracer("docs"), service="docs")]
)

manager = UserManager()
result = manager.runner().run(
    {"kind": "User", "version": "1.0.0", "name": "Alice"},
    "latest",
)

assert result["version"] == "2.0.0"
spans = exporter.get_finished_spans()
assert spans[0].name == "docs.migrate"
assert spans[0].attributes["migration.kind"] == "User"
assert spans[0].attributes["migration.strategy"] == "callable"
assert spans[0].attributes["migration.identity"] == "docs.otel.v1_v2"
```
