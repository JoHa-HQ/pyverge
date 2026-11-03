# Use FastMCP with pyverge

> Upgrading? `ToolDiscovery` is now `PyvergeProvider`. Attach it with
> `FastMCP(providers=[provider])`; see the
> [upgrade guide](../../reference/upgrades.md).

## Prerequisites

- Installed FastMCP adapter.
- A configured manager with registered models and migrations.

## Steps

### End-to-end example

```python
import asyncio
from typing import Literal

import semver
from fastmcp import Client, FastMCP
from fastmcp.tools import tool
from pydantic import BaseModel

from pyverge import Manager
from pyverge.adapters.fastmcp import PyvergeProvider
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
    PydanticModelAdapter(codec=ModelCodec(namespace="default", version_property="version", kind_property="kind")),
    on_missing="reconstruct_model",
)
WeatherManager.store_model(WeatherV2)
WeatherManager.store_migration(ManagerMigrationKey("search_weather", "1.0.0", "2.0.0"), add_wind)
manager = WeatherManager()

# Policy comes from each primitive's meta; the map is only a fallback.
discovery = PyvergeProvider(manager)


# 4. Attach the provider. FastMCP runs its startup before serving traffic.
server = FastMCP(
    "Weather",
    providers=[discovery],
    tools=[search_weather],
)


async def main() -> None:
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

### The lifecycle

Attaching the provider is enough. FastMCP enters `PyvergeProvider.lifespan()`
once at startup, after user lifespans and before it accepts traffic. The
provider then:

1. indexes every versioned server-owned component (`sync`);
2. materializes virtual versions when `virtual_versions=True` and attaches
   migration hooks (`enrich`);
3. applies the registry health policy (`validate_health`).

Virtual component projection is opt-in. Without `virtual_versions=True`, only
physical components are exposed.

```python
discovery = PyvergeProvider(manager, virtual_versions=True)
```

Components registered on the provider itself (`provider.tool(...)`,
`provider.prompt(...)`, `provider.resource(...)`) are indexed immediately.

#### Manual lifecycle

The phases remain public for hosts that own their startup ordering. They are
idempotent, so running them in a user lifespan and then again in the provider
lifespan is safe.

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(server: FastMCP):
    await discovery.sync(server)
    await discovery.enrich(server)
    discovery.validate_health()
    yield


server = FastMCP("Weather", providers=[discovery], lifespan=lifespan)
```

| Phase | What it does |
| --- | --- |
| `sync(server)` | Normalize every versioned server-owned component and register it through the manager. The registry reconciles duplicates and refreshes health. |
| `enrich(server)` | Materialize virtual primitives when `virtual_versions=True`, then attach migration hooks. Idempotent. |
| `validate_health()` | Read the registry health index at the configured fail level. |

`PyvergeExtension` optionally advertises the graph namespace and counts:

```python
from pyverge.adapters.fastmcp import PyvergeExtension

server.add_extension(PyvergeExtension(manager))
```

### Startup health validation

`validate_health()` asks the manager for registry health at the provider's fail
level. The registry owns the check and raises `HealthValidationError`; the
provider converts it to FastMCP's `FastMCPError`. The lifespan never yields, so
the transport never accepts traffic against an unhealthy graph.

The fail level is a logging-style threshold: `"info"` < `"warning"` < `"error"`,
plus `"never"` to disable blocking. The default is `"error"`. Structural
compatibility findings are `warning`s, so intentional breaking migrations still
start.

```python
discovery = PyvergeProvider(manager, health_fail_level="warning")
```

Ask the manager directly when you need the issues rather than a raise:

```python
issues = manager.health(fail_level="warning")   # raises HealthValidationError
issues = manager.health()                        # returns the tuple
```

Registration itself is registry-owned. `sync` hands each reflected node to
`manager.reconcile_model(...)`; the registry reconciles duplicates, reports
`ModelConflictError` on a drifting field surface, and updates its health index.
The adapter does not validate the graph a second time.

### Telemetry

The adapter is free of any tracing library. To trace calls, stack your own
FastMCP middleware; the `OtelAdapter` opens run and step spans **as current**,
so each migration span nests under the call span you open:

```python
from pyverge.runtime import OtelAdapter

class CallSpanMiddleware(Middleware):
    def __init__(self, tracer, service): ...
    async def on_call_tool(self, context, call_next):
        with self._tracer.start_as_current_span(f"{self._service}.call"):
            return await call_next(context)

server.middleware = [CallSpanMiddleware(tracer, "my-service")]
runner = manager.runtime(
    telemetry=(OtelAdapter(tracer=tracer, service="my-service"),)
).runner
```

See [Telemetry & Hooks](../../how-to/operations/instrument-migrations.md) for the
adapter. Step spans include graph namespace, kind, source/target, and migration
strategy/identity when available.

### Testing

The adapter is designed to be driven through the public server surface. See
[Testing approach](../../explanation/testing.md) for the layering rules and
[Test migrations](../../how-to/operations/test-migrations.md) for the worked
fixtures, plus the
[`showcases/fastmcp`](https://github.com/JoHa-HQ/pyverge/tree/main/showcases/fastmcp)
project (a layered FastMCP app with OpenTelemetry).

The provider lifespan runs once per runtime tree, on the first client session or
when serving over a transport. In-process `server.call_tool(...)` does **not**
enter the lifespan, so tests that call in-process should open one client session
first (see the showcase's `running_app`/`running_client` fixtures).

## Verify

```python
assert result.structured_content["wind"] == 0.0
```

## Troubleshooting

- Lifecycle not run: attach the provider with `providers=[discovery]`, or open a
  client session when driving the phases manually.
- Import error: install `pyverge[fastmcp]`.

## See also

- [FastMCP integration model](index.md)
- [FastMCP reference](reference.md)
