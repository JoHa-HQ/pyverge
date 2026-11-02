# FastMCP reference

## Component kinds

Each FastMCP primitive family is a `ComponentKind` adapter: it lists its
components, normalizes them into an `Entrance`, and materializes a
`VirtualComponent` back into the host. The provider depends only on the port and
defaults to all three adapters.

```python
from pyverge.adapters.fastmcp import (
    PromptKind,
    ResourceKind,
    ToolKind,
)

PyvergeProvider(manager, kinds=(ToolKind(), PromptKind()))
PyvergeProvider(
    manager,
    kinds=(ToolKind(), PromptKind(), ResourceKind(uri_scheme="weather://")),
)
```

Pass `kinds=` when only some primitive families should be indexed, for example
when a prompt and a resource share a graph kind and version.

Attach the provider to run the startup lifecycle:

```python
server = FastMCP("Weather", providers=[discovery], tools=[search_weather])
```

FastMCP enters the provider lifespan once, after user lifespans, and the
provider indexes server-owned components, materializes virtuals, attaches
hooks, and validates registry health before serving.

- A primitive is indexed only if it declares a `version`. Unversioned
  primitives pass through untouched.
- A kind's **policy** (its convergence target) is declared per component:
  `meta={"policy": ...}`. The `policies={kind: policy}` map is only a fallback for
  components that cannot declare one. Every exposed kind needs a policy; there is
  no silent default, and all versions of a kind must agree. The resolved policy
  is stored on each `Entrance`, so the component is the source of truth.
  `"latest"`/`"earliest"` pick the chain ends; a pinned value selects that
  version. A **bounded range** resolves to the highest matching version:

  ```python
  from pyverge.adapters.fastmcp import VersionRange

  PyvergeProvider(
      manager,
      policies={"User": VersionRange(gte="1.0.0", lt="3.0.0")},
  )
  ```

  In `meta`, the same range is `{"gte": "1.0.0", "lt": "3.0.0"}` (or `eq`).
- A policy may be **per-kind** — `{"*": "latest", "Address": "earliest"}` — which
  also steers the **nested** kinds embedded in the payload: each converts to its
  own target while the outer kind converges to the `"*"` target.
- `ResourceKind(uri_scheme=...)` prefixes virtual resource templates so they
  match the physical ones (e.g. `weather://{city}{?units}`).
- `transforms=(...)` are applied after `sync` and `enrich`, so a listing
  transform such as `VersionFilter` cannot hide physical components from
  indexing.
- FastMCP native `Depends` parameters are wiring, not payload. FastMCP excludes
  them from the reflected contract — see [Injected parameters](#injected-parameters).

## Migration context

`PyvergeProvider` forwards a migration context and run ID to the runner:

```python
from pyverge.core import MigrationContext

discovery = PyvergeProvider(
    manager,
    context=MigrationContext.create({"tenant": "acme"}),
    run_id="startup",
)
```

For per-request context, use a factory. It receives the active FastMCP
`Context` when one is available:

```python
discovery = PyvergeProvider(
    manager,
    context_factory=lambda ctx: MigrationContext.create(
        {"session": ctx.session_id}
    ),
)
```

The provider also accepts `validate_target=True` to validate each converged
entry against its target model. Context and run ID reach migrations, hooks, and
middleware unchanged.

## Injected parameters

Use FastMCP's native `Depends` for wiring, not payload:

```python
from fastmcp.dependencies import Depends
from fastmcp.tools import tool


def get_weather_service() -> WeatherService: ...


@tool(name="search_weather", version="2.0.0")
def search_weather(
    city: str,
    weather: WeatherService = Depends(get_weather_service),
) -> dict: ...
```

FastMCP excludes dependency parameters from the tool, prompt, or resource
schema and resolves them at call time. Pyverge no longer rewrites signatures for
dependency injection.

Virtual components also resolve native FastMCP dependencies before invoking
the anchor handler.

## See also

- [Managers](../../explanation/managers.md) — the bounded-context invariant the adapter relies on.
- [Migrations](../../explanation/migrations.md) — reconstructing missing models and migrations.
- [Execution Flow](../../explanation/execution-flow.md) — discovery, ordering, and finalize.
- [Telemetry & Hooks](../../how-to/operations/instrument-migrations.md) — per-step spans and call-level tracing.
