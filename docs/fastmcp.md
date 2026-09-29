# FastMCP Integration

pyverge plugs into a [FastMCP](https://github.com/jlowin/fastmcp) server as an
adapter: your server keeps declaring FastMCP primitives (tools, prompts,
resources), and pyverge reflects each versioned primitive into a version graph,
then converges every call's arguments to the policy target before the handler
runs.

The adapter lives in `pyverge.adapters.fastmcp`. pyverge core and its ports never
import FastMCP — everything here is an adapter-local composition over one
`Manager` and one server.

```bash
pip install "pyverge[cli]" fastmcp
```

## The model

Nothing new is invented: pyverge reflects FastMCP primitives into ordinary pyverge
models and migrations.

- **Physical primitive** — a FastMCP tool/prompt/resource registered at a
  `version`. Its reflected `inputSchema` is an *anchor*: the model is registered
  from it (or reconciled against a hand-registered model).
- **Virtual primitive** — for every other version of that kind, the adapter
  materializes a primitive whose handler converges arguments to the policy target
  and then calls the physical anchor. Older callers see the version they declared;
  the handler always receives the target shape.
- **Convergence** — a versioned call is negotiated natively (FastMCP's
  `version=`) and routed to the virtual primitive, which converges the outer
  payload. `ConvergeMiddleware` covers the one case native routing cannot see: a
  plain tool whose arguments **embed** versioned models.

Versioning is FastMCP's, end to end — pyverge adds no calling convention of its
own.

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
    ConvergeMiddleware,
    ToolDiscovery,
    ToolReflection,
    tool,
)
from pyverge.migration import MigrationSettings, PydanticModelAdapter
from pyverge.types import ManagerMigrationKey


# 1. The anchor model: the newest shape (v2).
class WeatherV2(BaseModel):
    kind: Literal["search_weather"] = "search_weather"
    version: Literal["2.0.0"] = "2.0.0"
    city: str
    temperature: float = 0.0
    wind: float = 0.0


# 2. The migration that reconstructs v1 from v2.
def add_wind(data: dict) -> dict:
    return {**data, "wind": 0.0}


# 3. The physical tool — its signature is the v2 contract.
@tool(name="search_weather", version="2.0.0")
def search_weather(city: str, temperature: float = 0.0, wind: float = 0.0) -> dict:
    return {"city": city, "temperature": temperature, "wind": wind}


manager = Manager[semver.Version].configure(
    MigrationSettings(on_missing="reconstruct_model"),
    PydanticModelAdapter(),
)()
manager.store_model(WeatherV2)
manager.store_migration(ManagerMigrationKey("search_weather", "1.0.0", "2.0.0"), add_wind)

discovery = ToolDiscovery(
    manager,
    [ToolReflection(manager.adapter)],
    policies={"search_weather": "latest"},
)


# 4. The lifecycle is the server's lifespan — the user wires it.
@asynccontextmanager
async def lifespan(server: FastMCP):
    await discovery.search(server)
    discovery.register()
    await discovery.enrich(server)
    yield


server = FastMCP(
    "Weather",
    lifespan=lifespan,
    tools=[search_weather],
)
server.middleware = [ConvergeMiddleware(discovery)]


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

## The lifecycle

`ToolDiscovery` owns three phases. **The lifespan is the user's concern** —
FastMCP's model is that setup runs once at startup, so wire the phases into a
lifespan you hand to `FastMCP(lifespan=...)` (see the example above). FastMCP
enters it on the first client session or when serving over a transport.

| Phase | What it does |
| --- | --- |
| `search(server)` | Traverse the reflection providers; index every versioned primitive the manager owns and a policy covers. Idempotent — re-running rebuilds the index. |
| `register()` | Reflect each indexed node's schema, materialize it as its anchor model, then validate the registered graph's references. |
| `enrich(server)` | Precompute convergence paths, materialize the virtual primitives, attach the migration hooks. Run once — re-running re-materializes the virtuals. |

The phases are also public methods, so a lifespan can compose them with other
startup work (OpenTelemetry providers, DB pools, …) and teardown in `finally`.

`register()` enforces two invariants, both through the engine:

- **Field agreement** — a reflected schema that drifts from an already-registered
  model raises `ModelConflictError` (naming the host primitive), unless identical.
- **Reference completeness** — a model referencing an unregistered versioned kind
  raises `MissingReferenceError`.

Both exceptions carry structured attributes (`missing`/`extra`, `absent`) and a
resolution hint, so a startup failure tells you exactly which primitive drifted and
how to fix it.

## Reflection providers

A provider is the factory bridging one FastMCP primitive type to the graph. Bind
one per type you expose; it traverses that type, emits a normalized node per
versioned primitive, and materializes virtuals of the same type.

```python
from pyverge.adapters.fastmcp import PromptReflection, ResourceReflection

providers = [
    ToolReflection(manager.adapter),
    PromptReflection(manager.adapter),
    ResourceReflection(manager.adapter, uri_scheme="weather://"),
]
```

- A primitive is indexed only if it declares a `version` and its kind is
  registered in the manager. Unversioned primitives pass through untouched. A
  versioned primitive of an owned kind with no recorded policy fails fast — every
  exposed kind needs an explicit policy; there is no silent default.
- `ResourceReflection` takes the URI `scheme`/prefix so virtual templates match the
  physical ones (e.g. `weather://{city}{?units}`).
- A provider also hides **injected** parameters (wiring, not payload) from the
  reflected contract. The `tool`/`prompt`/`resource` decorators apply the same
  rule to a physical function's signature — see
  [Injected parameters](#injected-parameters).

## Convergence middleware

`ConvergeMiddleware` handles the one thing FastMCP's native version routing
cannot see: a **plain** tool whose arguments embed versioned models — a nested
entry carrying its own `kind`/`version`. It migrates each embedded entry in
place, then forwards to the tool's handler.

```python
server.middleware = [ConvergeMiddleware(discovery)]
```

A natively versioned call is left untouched: FastMCP routes it to the matching
virtual primitive, which converges the outer payload. There is no
pyverge-specific version convention — versioning is FastMCP's, end to end.

Telemetry is deliberately **not** the middleware's concern. To trace calls, stack
your own middleware around it — the adapter is free of any tracing library:

```python
class CallSpanMiddleware(Middleware):
    def __init__(self, tracer, service): ...
    async def on_call_tool(self, context, call_next):
        with self._tracer.start_as_current_span(f"{self._service}.call"):
            return await call_next(context)

server.middleware = [CallSpanMiddleware(tracer, "my-service"), ConvergeMiddleware(discovery)]
```

Because the per-migration `OTELHook`s open their spans **as current**, each step
span nests under the call span your middleware opened. See
[Telemetry & Hooks](telemetry.md).

## Injected parameters

A dependency-injected parameter (e.g. `Provide[...]`, `Depends(...)`) is wiring,
not payload, and must not appear in the reflected schema. Wrap each physical
function with the matching decorator — `tool`, `prompt`, or `resource` — which
builds the FastMCP component with its injected parameters hidden:

```python
from pyverge.adapters.fastmcp import prompt, resource, tool


@tool(name="search_weather", version="2.0.0")
@inject
def search_weather(city: str, weather: WeatherService = Provide[...]) -> dict: ...


@prompt(name="weather_briefing", version="2.0.0")
@inject
def weather_briefing(city: str, weather: WeatherService = Provide[...]) -> str: ...


@resource(uri_template="weather://{city}", name="weather_reading", version="2.0.0")
@inject
def weather_reading(city: str, weather: WeatherService = Provide[...]) -> str: ...
```

Apply the decorator **outside** `@inject` so it sees the raw signature (the
injected parameter is hidden, then `@inject` still fills it at call time). Each
decorator also works as a plain factory: `tool(fn, name=..., version=...)`.

`hide_injected(fn)` is the underlying helper if you only want to rewrite a
signature in place. The default detector recognizes `dependency_injector`'s
`Provide` and FastMCP's `Depends`; `never_injected` disables detection,
`marker_detector(*types)` matches your own, and the reflection providers apply
the same detector when reflecting.

## Testing

The adapter is designed to be driven through the public server surface. See the
[Testing](testing.md) guide and the worked
[`showcases/fastmcp`](https://github.com/JoHa-HQ/pyverge/tree/main/showcases/fastmcp)
project (a layered FastMCP app with `dependency-injector` and OpenTelemetry).

## See also

- [Managers](managers.md) — the bounded-context invariant the adapter relies on.
- [Migrations](migration.md) — reconstructing missing models and migrations.
- [Execution Flow](execution-flow.md) — discovery, ordering, and finalize.
- [Telemetry & Hooks](telemetry.md) — per-step spans and call-level tracing.
