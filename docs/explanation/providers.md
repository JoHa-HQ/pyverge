# Providers

A provider adapts one model system to the engine. Discovery, planning, and
execution operate on payloads; the provider owns model identity, schema
inspection, validation, and conversion.

## Protocol layout

`ModelAdapter` is the aggregate adapter seam. Shared behavior lives in
`ModelCodec`:

| Component | Responsibility |
| --- | --- |
| `ModelCodec` | version/kind keys, parsing, payload validation, Pydantic reflection |
| `ModelAdapter` | provider-specific container identification, fields, references, model materialization |
| `AbstractModelAdapter` | provider-neutral composition: versionable nodes, descriptors, diff, materialize |

Every adapter receives a `ModelCodec`:

```python
from pyverge.schemas import ModelCodec, PydanticModelAdapter

adapter = PydanticModelAdapter(codec=ModelCodec())
```

`ModelCodec` is required. It carries `version_property` / `kind_property` and
the Pydantic payload/reflection strategy shared by Pydantic-backed providers.

## Container checks

Container handling has two modes:

```python
adapter.can_handle(container)
adapter.can_handle(container, fields=frozenset({"name", "age"}))
```

- `can_handle(container)` answers: is this a container type this provider understands?
- `can_handle(container, fields=...)` asks whether the container can represent every migrated field.

The extractor uses the first form. The execution compatibility gate uses the
field-aware form.

## Field surface

```python
adapter.fields(model_cls)
```

Returns the model's payload fields, excluding the configured identity fields
(`version` and `kind` by default). Identity encoding belongs to the graph, not
the payload contract.

## Shipped adapters

- `PydanticModelAdapter`
- `JsonSchemaModelAdapter`
- `DataclassModelAdapter`

`PydanticModelAdapter` and `JsonSchemaModelAdapter` use Pydantic model classes as
the runtime container; the JSON Schema adapter materializes schemas into
Pydantic models at registration time. Both consume `ModelCodec` directly.

`DataclassModelAdapter` uses stdlib `dataclasses` classes as the runtime
container. Identity and payload behavior come from `ModelCodec`; `dataclass`
reflection stays adapter-local.

Migration backends live in `pyverge.migrations`. Import schema adapters
from `pyverge.schemas`.

## Planned adapters

- Avro (`pyverge-avro`)
- Protobuf (`pyverge-protobuf`)

These are roadmap items, not shipped. Do not assume their APIs are stable.

## Adding a provider

Subclass `AbstractModelAdapter`, inject `ModelCodec`, and implement the
provider-specific reflection hooks.

```python
from pyverge.schemas import ModelCodec
from pyverge.schemas.base import AbstractModelAdapter


class MyModelAdapter(AbstractModelAdapter):
    def __init__(self, codec: ModelCodec) -> None:
        super().__init__(codec)

    def identify(self, model_cls):
        ...

    def can_handle(self, container, *, fields=None):
        ...

    def describe_fields(self, model_cls):
        ...

    def resolve_model(self, annotation):
        ...

    def field_model(self, parent_model, field_name):
        ...
```

Provider adapters must not import the engine, registry, or manager. The
manager resolves a `MigrationSpec` to a `MigrationFunc`; the adapter never
registers migrations itself.

## Date versioning

Versions can also be ISO calendar dates instead of semver. Use
`pendulum.Date` as the version strategy:

```python
import pendulum
from typing import Literal

from pyverge import Manager
from pyverge.schemas import ModelCodec, PydanticModelAdapter

UserManager = Manager[pendulum.Date].configure(
    PydanticModelAdapter(codec=ModelCodec()),
)


@UserManager.model()
class UserV20250310(BaseModel):
    kind: Literal["User"] = "User"
    version: Literal["2025-03-10"] = "2025-03-10"
    name: str
    email: str
```

The engine orders date versions chronologically and migrates across them the
same way as semver. Version strings are parsed by
`ModelCodec`, which understands both formats.
