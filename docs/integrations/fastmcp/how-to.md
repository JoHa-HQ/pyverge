# Use FastMCP with pyverge

> Upgrading? `ToolDiscovery` is now `FastMCPDiscovery`, and registration is
> `await discovery.register(server)`. See the
> [upgrade guide](../../reference/upgrades.md).

## Prerequisites

- Installed FastMCP adapter.
- A configured manager with registered models and migrations.

## Steps

## End-to-end example

```python
import asyncio
from contextlib import asynccontextmanager
from typing import Literal

import semver
from fastmcp import Client, FastMCP
from pydantic import BaseModel

from pyverge import Manager
from pyverge.adapters.fastmcp import (
    FastMCPDiscovery,
    PromptReflection,
    ResourceReflection,
    ToolReflection,
    tool,
)
from pyverge.schemas import ModelCodec, PydanticModelAdapter
from pyverge.types import ManagerMigrationKey


# 1. The anchor model: the newest shape (v2).
class WeatherV2(BaseModel):
    kind: Literal["search_weather"] = "search_weather"
    version: Literal["2.0.0"] = "2.0.0"
    city: str
    temperature: float = 0.0
    wind: float = 0.0


# 2. The migration that reconstructs v1 from v2.
def add_wind(data: dict, context=None) -> dict:
    return {**data, "wind": 0.0}


# 3. The physical tool — its signature is the v2 contract; meta declares policy.
@tool(name="search_weather", version="2.0.0", meta={"policy": "latest"})
def search_weather(city: str, temperature: float = 0.0, wind: float = 0.0) -> dict:
    return {"city": city, "temperature": temperature, "wind": wind}


WeatherManager = Manager[semver.Version].configure(
    PydanticModelAdapter(codec=ModelCodec(namespace="", version_property="version", kind_property="kind")),
    on_missing="reconstruct_model",
)
WeatherManager.store_model(WeatherV2)
WeatherManager.store_migration(ManagerMigrationKey("search_weather", "1.0.0", "2.0.0"), add_wind)
manager = WeatherManager()

# Policy comes from each primitive's meta; the map is only a fallback.
discovery = FastMCPDiscovery(
    manager,
    [
        ToolReflection(manager.adapter),
        PromptReflection(manager.adapter),
        ResourceReflection(manager.adapter),
    ],
)


# 4. The lifecycle is the server's lifespan — the user wires it.
@asynccontextmanager
async def lifespan(server: FastMCP):
    await discovery.search(server)
    await discovery.register(server)
    await discovery.enrich(server)
    yield


server = FastMCP(
    "Weather",
    lifespan=lifespan,
    tools=[search_weather],
)


async def main() -> None:
    # FastMCP enters the lifespan on the client session, then serves.
    async with Client(server) as client:
        # Version is negotiated natively — the same `version=` every FastMCP
        # client uses; the framework routes the call to the matching primitive.
        result = await client.call_tool(
            "search_weather", {"city": "Berlin"}, version="1.0.0"
        )
        assert result.structured_content["wind"] == 0.0


asyncio.run(main())
```

The call returns the v2 shape; the handler never sees a v1 payload. There is no
pyverge-specific calling convention — a caller uses FastMCP's native `version=`,
exactly as with any versioned component.

The lifecycle runs **once**, when FastMCP enters the server's lifespan — on the
first client session or when serving over a transport. In-process
`server.call_tool(...)` does **not** enter the lifespan, so tests that call
in-process should prime it with one client session first (see the showcase's
`running_app`/`running_client` fixtures).

### The lifecycle

`FastMCPDiscovery` owns three phases. **The lifespan is the user's concern** —
FastMCP's model is that setup runs once at startup, so wire the phases into a
lifespan you hand to `FastMCP(lifespan=...)` (see the example above). FastMCP
enters it on the first client session or when serving over a transport.

| Phase | What it does |
| --- | --- |
| `search(server)` | Traverse the reflection providers; index every versioned primitive the manager owns and a policy covers. Idempotent — re-running rebuilds the index. |
| `register(server)` | Reflect each indexed node's schema, materialize it as its anchor model, then validate the registered graph's references. |
| `enrich(server)` | Precompute convergence paths, materialize the virtual primitives, attach the migration hooks. Run once — re-running re-materializes the virtuals. |

The phases are also public methods, so a lifespan can compose them with other
startup work (OpenTelemetry providers, DB pools, …) and teardown in `finally`.

`register(server)` enforces two invariants, both through the engine:

- **Field agreement** — a reflected schema that drifts from an already-registered
  model raises `ModelConflictError` (naming the host primitive), unless identical.
- **Reference completeness** — a model referencing an unregistered versioned kind
  raises `MissingReferenceError`.

Both exceptions carry structured attributes (`missing`/`extra`, `absent`) and a
resolution hint, so a startup failure tells you exactly which primitive drifted and
how to fix it.

### Telemetry

The adapter is free of any tracing library. To trace calls, stack your own
FastMCP middleware; the per-migration `OTELHook`s open their spans **as
current**, so each step span nests under the call span you open:

```python
class CallSpanMiddleware(Middleware):
    def __init__(self, tracer, service): ...
    async def on_call_tool(self, context, call_next):
        with self._tracer.start_as_current_span(f"{self._service}.call"):
            return await call_next(context)

server.middleware = [CallSpanMiddleware(tracer, "my-service")]
```

See [Telemetry & Hooks](../../how-to/operations/instrument-migrations.md) for the per-step `OTELHook`. Step spans include graph namespace, kind, source/target, and migration strategy/identity when available.

### Testing

The adapter is designed to be driven through the public server surface. See the
[Testing](../../how-to/operations/test-migrations.md) guide and the worked
[`showcases/fastmcp`](https://github.com/JoHa-HQ/pyverge/tree/main/showcases/fastmcp)
project (a layered FastMCP app with `dependency-injector` and OpenTelemetry).

## Verify

```python
assert result.structured_content["wind"] == 0.0
```

## Troubleshooting

- Lifecycle not run: open a client session.
- Import error: install `pyverge[fastmcp]`.

## See also

- [FastMCP integration model](index.md)
- [FastMCP reference](reference.md)
