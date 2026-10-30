# Upgrade guide

Compatibility notes for the execution/registration architecture change.

## What did not change

- `Manager` remains the public entry point.
- `@Manager.model()` and `@Manager.migration(...)` remain.
- JSON Patch, JSONata, and Python callable migrations remain.
- Target policies remain: `latest`, `earliest`, pinned, per-kind, model, skip.
- Registry graph semantics, compatibility checks, hooks, and CLI remain.
- `MigrationSettings` remains available as a settings bag.

## Compatibility matrix

| Before | After |
| --- | --- |
| `Manager.configure(settings, adapter)` | `Manager.configure(adapter, **manager_kwargs(settings))` |
| `manager.migrate(payload, target)` | `manager.runner().run(payload, target)` |
| `await manager.amigrate(payload, target)` | `await manager.runner(runtime=AsyncBackend(...)).run(payload, target)` |
| `manager.delegate()` / `manager.prepare()` | removed; build a `Runner` and reuse it |
| `MigrationSettings(execution_mode=...)` | choose `ThreadedBackend`, `AsyncBackend`, or `ProcessBackend` |
| `MigrationSettings(parallel_workers=...)` | backend `max_workers` |
| `pyverge.migration.*` | `pyverge.engine`, `pyverge.registry`, `pyverge.schemas`, `pyverge.migrations`, `pyverge.versioning` |
| `ToolDiscovery` | `FastMCPDiscovery` |
| `discovery.register()` | `await discovery.register(server)` |
| `Reflector(manager)` FastStream startup hook | explicit model/migration registration before runtime |

## Model codec

Adapters now require an explicit `ModelCodec`:

```python
from pyverge.schemas import ModelCodec, PydanticModelAdapter

adapter = PydanticModelAdapter(
    codec=ModelCodec(namespace="", version_property="version", kind_property="kind")
)
```

## `MigrationSettings`

`MigrationSettings` still exists. It is no longer passed directly to
`Manager.configure`.

```python
from pyverge import Manager
from pyverge.schemas import ModelCodec, PydanticModelAdapter
from pyverge.settings import MigrationSettings, manager_kwargs

settings = MigrationSettings(on_missing="reconstruct_model")
UserManager = Manager[semver.Version].configure(
    PydanticModelAdapter(codec=ModelCodec(namespace="", version_property="version", kind_property="kind")),
    **manager_kwargs(settings),
)
```

Field mapping:

| Setting | Destination |
| --- | --- |
| `on_missing` | `Manager.configure(on_missing=...)` |
| `direction` | `manager.runner(direction=...)` |
| `on_direction_violation` | `manager.runner(...)` |
| `on_missing_path` | `manager.runner(...)` |
| `on_depth_violation` | `manager.runner(...)` |
| `validation_mode` | `manager.runner(validation_mode=...)` |
| `max_migration_depth` | `Runner.run(max_depth=...)` |
| `execution_mode` | backend choice |
| `parallel_workers` | backend `max_workers` |
| `version_property` / `kind_property` | `ModelCodec(...)` passed to adapter |

## Sync execution

Before:

```python
migrated = manager.migrate(payload, target="latest")
```

After:

```python
migrated = manager.runner().run(payload, "latest")
```

`Runner.run()` defaults:

```text
container=None
max_depth=-1
context=None
```

## Async execution

Before:

```python
result = await manager.amigrate(payload, target="latest")
```

After:

```python
from pyverge.execution import AsyncBackend

runner = manager.runner(
    runtime=AsyncBackend(
        backend="asyncio",
        backend_options={},
        max_workers=4,
    )
)
result = await runner.run(payload, "latest")
```

## Process isolation

```python
from pyverge.execution import ProcessBackend

backend = ProcessBackend(max_workers=2)
try:
    result = manager.runner(runtime=backend).run(payload, "latest")
finally:
    backend.close()
```

## Runtime context

```python
result = manager.runner().run(
    payload,
    "latest",
    context={"tenant_id": "tenant_99"},
)
```

## Graph identity

`VersionKey` and `EdgeKey` are now first-class identity primitives. A node ID
carries the namespace, kind, and parsed version; keys add identity-neutral
storage metadata.

```python
from pyverge.versioning import EdgeKey, NodeId, VersionKey, VersionNode

node_id = NodeId("com.joha.order", "Order", "1.0.0")
key = VersionKey(
    namespace=node_id.namespace,
    kind=node_id.kind,
    version=node_id.version,
    ref=storage_ref,
)
edge = EdgeKey(
    source=node_id,
    target=NodeId("com.joha.order", "Order", "2.0.0"),
)
```

One registry owns one namespace. The manager defaults an empty namespace.
Cross-namespace edges are forbidden. Identity objects no longer expose
`jgf_id`; JGF/export renders namespace-prefixed external IDs.

Descriptor references are `NodeId` values and therefore carry their namespace
through canonical serialization, missing-reference checks, and JGF/manifest
export. A registry resolves an empty reference namespace against its own
namespace. Explicit foreign-namespace references remain unresolved unless that
identity is present in the same registry; cross-namespace edges are rejected.

## Import moves

```python
from pyverge.engine import Engine
from pyverge.registry import Registry
from pyverge.schemas import ModelCodec, PydanticModelAdapter
from pyverge.versioning import EdgeKey, NodeId, VersionKey, VersionNode
```

`pyverge.migration` is gone.

## FastMCP

```text
ToolDiscovery -> FastMCPDiscovery
```

```python
from pyverge.adapters.fastmcp import FastMCPDiscovery, ToolReflection

discovery = FastMCPDiscovery(manager, [ToolReflection(manager.adapter)])
```

Lifecycle:

```python
await discovery.search(server)
await discovery.register(server)
await discovery.enrich(server)
```

## FastStream

The old `Reflector(manager)` startup hook is gone. Register models and
migrations before constructing the runtime manager:

```python
from pyverge.types import ManagerMigrationKey

OrderManager = Manager[semver.Version].configure(PydanticModelAdapter(codec=ModelCodec(namespace="", version_property="version", kind_property="kind")))
OrderManager.store_model(Order)
OrderManager.store_migration(
    ManagerMigrationKey("Order", "1.0.0", "2.0.0"),
    add_currency,
)
manager = OrderManager()
```

## Descriptor registration

`SourceDescriptor` string strategies were replaced by typed descriptors and
registration commands:

```text
ModelDescriptor      -> RegisterModel
MigrationDescriptor  -> RegisterMigration
```

Sources emit descriptors. Managers collect commands and execute them through
`Engine.register`.

## Troubleshooting

### `ImportError: No module named pyverge.migration`

Use the owning contexts:

```python
from pyverge.engine import Engine
from pyverge.registry import Registry
from pyverge.schemas import ModelCodec, PydanticModelAdapter
from pyverge.versioning import EdgeKey, VersionNode
```

### `manager` has no `migrate` or `amigrate`

Use `manager.runner().run(...)` and select async/process execution with a
backend.

### Async required / sync required

The backend determines execution mode. Use `AsyncBackend` for coroutine
migrations and await the runner result.

### `TypeError: configure() got an unexpected keyword argument`

`Manager.configure` accepts individual keyword options directly:

```python
Manager.configure(
    PydanticModelAdapter(codec=ModelCodec(namespace="", version_property="version", kind_property="kind")),
    on_missing="raise",
    namespace="com.joha.order",
)
```

### FastMCP startup fails after upgrade

Replace `ToolDiscovery` with `FastMCPDiscovery` and call
`await discovery.register(server)`.

### FastStream subscriber receives the old version

Register models and migrations on the manager class before constructing the
runtime instance. The runtime instance owns a copy of the graph.
