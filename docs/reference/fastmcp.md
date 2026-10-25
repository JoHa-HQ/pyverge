# FastMCP reference

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
  registered in the manager. Unversioned primitives pass through untouched.
- A kind's **policy** (its convergence target) comes from the primitive's own
  declaration — `meta={"policy": ...}` — or the discovery's
  `policies={kind: policy}` map. Every exposed kind needs one; there is no silent
  default, and all versions of a kind must agree. `"latest"`/`"earliest"` pick
  the chain ends; any other value is a pinned version, resolved by the manager at
  migrate time.
- A policy may be **per-kind** — `{"*": "latest", "Address": "earliest"}` — which
  also steers the **nested** kinds embedded in the payload: each converts to its
  own target while the outer kind converges to the `"*"` target.
- `ResourceReflection` takes the URI `scheme`/prefix so virtual templates match the
  physical ones (e.g. `weather://{city}{?units}`).
- A provider also hides **injected** parameters (wiring, not payload) from the
  reflected contract. The `tool`/`prompt`/`resource` decorators apply the same
  rule to a physical function's signature — see
  [Injected parameters#injected-parameters.

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

## See also

- [Managers](../explanation/managers.md) — the bounded-context invariant the adapter relies on.
- [Migrations](../explanation/migrations.md) — reconstructing missing models and migrations.
- [Execution Flow](../explanation/execution-flow.md) — discovery, ordering, and finalize.
- [Telemetry & Hooks](../how-to/telemetry.md) — per-step spans and call-level tracing.
