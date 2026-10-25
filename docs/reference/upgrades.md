# Upgrade guide

Breaking API changes and their replacements.

## `ToolDiscovery` renamed

```text
ToolDiscovery -> FastMCPDiscovery
```

The orchestrator handles tools, prompts, and resources — not only tools.

```python
from pyverge.adapters.fastmcp import FastMCPDiscovery, ToolReflection

discovery = FastMCPDiscovery(manager, [ToolReflection(manager.adapter)])
```

## `manager.migrate()` removed

Use a runner:

```python
runner = manager.runner()
result = runner.run(payload, "latest")
```

Async execution is selected by the backend:

```python
from pyverge.execution import AsyncBackend

runner = manager.runner(
    runtime=AsyncBackend(backend="asyncio", backend_options={}, max_workers=4)
)
result = await runner.run(payload, "latest")
```

## `pyverge.migration` package removed

Use the owning contexts:

```python
from pyverge.engine import Engine
from pyverge.providers import PydanticModelAdapter
from pyverge.registry import Registry
from pyverge.versioning import EdgeKey, VersionNode
```

## Descriptor registration

`SourceDescriptor` string strategies were replaced by typed descriptors and registration commands:

```text
ModelDescriptor      -> RegisterModel
MigrationDescriptor  -> RegisterMigration
```

Sources emit descriptors. Managers collect commands and execute them through `Engine.register`.

## `Reflector` startup hook removed

FastStream source registration is explicit on the manager graph. FastMCP lifecycle registration now runs through `FastMCPDiscovery.register(server)`.
