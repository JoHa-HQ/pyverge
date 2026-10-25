# Managers

A `Manager` is a **bounded context** — one version graph, one registry, one
adapter. This page explains the bounded-context invariant and how it shapes manager
organization. See [Register models and migrations](../how-to/register-models.md)
for the task.

## The invariant

> A manager owns one complete version graph: register a kind **and every kind it
> transitively contains** in the same manager.

The unit of ownership is not "a kind" — it is **the whole graph rooted at a
source**. If a payload can reach a kind, that kind must live in the manager that
handles the payload.

## Which manager owns what

A model belongs to the manager that owns its **whole version graph** — the kind
and every kind it transitively contains. The rest of this page explains why.

## Why: three engine mechanics

The engine assumes a single registry end to end. Splitting a graph breaks all
three stages:

1. **Discovery** — the walker resolves nested kinds against *one* registry. A
   kind missing from that registry is invisible: never discovered, never
   migrated.
2. **Ordering** — the dependency graph derives parent/child edges from the
   registry's version list for each kind. A split graph loses the containment
   edge, so execution order is no longer guaranteed (children before parents).
3. **Finalize** — the migrated payload is validated against the target model. A
   nested entry absent from that model is **silently dropped**.

## What "per source" means

Group registrations by the **system whose data converges together** — a service,
an MCP tool server, a tenant track — not by kind, file, or team ownership.

```python
# One bounded context: the Weather service, its own complete graph.
WeatherManager = Manager[semver.Version].configure(
    JsonSchemaModelAdapter(),
)

# Everything Weather can reach lives here: the tool kind AND its nested kinds.
WeatherManager.store_model(search_weather_v1)
WeatherManager.store_model(search_weather_v2)
WeatherManager.store_model(location_v1)   # nested inside search_weather
WeatherManager.store_model(location_v2)
WeatherManager.store_migration(
    ManagerMigrationKey("search_weather", "1.0.0", "2.0.0"), ...
)
WeatherManager.store_migration(
    ManagerMigrationKey("location", "1.0.0", "2.0.0"), ...
)
manager = WeatherManager()
```

The same rule applies to decorator registration: every `@Manager.model()` for a
graph belongs to the same manager class.

## Failure modes

Splitting a graph across managers does not raise — it produces **partial or
lossy** migrations:

```python
# location lives in A, user lives in B, but a user payload embeds a location.
A().runner().run(user_payload, "latest")   # location converges; parent user left at 1.0.0
B().runner().run(user_payload, "latest")   # user converges; nested location silently dropped
```

| Symptom | Cause |
| --- | --- |
| Nested entries never migrate | kind not in the handling manager's registry |
| Parent migrated but children stale | missing containment edge -> wrong order |
| Fields vanish after migration | nested entry not in the target model -> dropped at finalize |

The FastMCP adapter follows this invariant directly: `FastMCPDiscovery` binds
**one** manager, so there is no routing to do — the manager owns the whole graph
and every tool kind resolves within it.

## See also

- [Getting Started](../tutorials/getting-started.md) — a minimal end-to-end example.
- [Migrations](migrations.md) — reconstruct missing models or migrations.
- [Execution Flow](execution-flow.md) — discovery, ordering, and finalize.
