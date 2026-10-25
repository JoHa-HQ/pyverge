# Providers

A provider adapts one model system to the engine. Discovery, planning, and
execution operate on payloads; the provider owns model identity, schema
inspection, validation, and conversion.

## Protocol layout

`ModelAdapter` is the aggregate seam. It composes four narrow protocols:

| Protocol | Responsibility |
| --- | --- |
| `ModelIdentity` | version/kind extraction, version parsing, versionable construction |
| `ModelSchema` | field discovery, nested model resolution, container shape |
| `ModelRuntime` | validation, finalization, instantiation, serialization |
| `ModelReflection` | schema diffing, model reconstruction, migration proposal |

Consumers can depend on the narrow protocol they need. Implementations must
satisfy the aggregate `ModelAdapter`.

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

Both use Pydantic model classes as the runtime container; the JSON Schema
adapter materializes schemas into Pydantic models at registration time.

## Adding a provider

Subclass `AbstractModelAdapter` and implement the four protocol areas. The
shared base supplies version parsing, property handling, `fields`, and the
default `can_handle -> identify` relationship.

```python
from pyverge.schemas.base import AbstractModelAdapter


class MyModelAdapter(AbstractModelAdapter):
    def identify(self, model_cls):
        return ...

    def version(self, model_cls):
        ...

    def kind(self, model_cls):
        ...

    def can_handle(self, container, *, fields=None):
        ...
```

Provider adapters must not import the engine, registry, or manager. The
manager resolves a `MigrationSpec` to a `MigrationFunc`; the adapter never
registers migrations itself.
