# Manager Organization

A `Manager` is a **bounded context** — one version graph, one registry, one
adapter. This page explains the invariant that makes that true, why the engine
cannot work across a split graph, and how to organize several managers safely.

## The invariant

> A manager owns one complete version graph: register a kind **and every kind it
> transitively contains** in the same manager.

The unit of ownership is not "a kind" — it is **the whole graph rooted at a
source**. If a payload can reach a kind, that kind must live in the manager that
handles the payload.

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
    MigrationSettings(),
    JsonSchemaModelAdapter(),
)

# Everything Weather can reach lives here: the tool kind AND its nested kinds.
manager.store_model(search_weather_v1)
manager.store_model(search_weather_v2)
manager.store_model(location_v1)   # nested inside search_weather
manager.store_model(location_v2)
manager.store_migration(("search_weather", "1.0.0", "2.0.0"), ...)
manager.store_migration(("location", "1.0.0", "2.0.0"), ...)
```

The same rule applies to decorator registration: every `@Manager.model()` for a
graph belongs to the same manager class.

## Failure modes

Splitting a graph across managers does not raise — it produces **partial or
lossy** migrations:

```python
# location lives in A, user lives in B, but a user payload embeds a location.
A.migrate(user_payload)   # location converges; parent user left at 1.0.0
B.migrate(user_payload)   # user converges; nested location silently dropped
```

| Symptom | Cause |
| --- | --- |
| Nested entries never migrate | kind not in the handling manager's registry |
| Parent migrated but children stale | missing containment edge -> wrong order |
| Fields vanish after migration | nested entry not in the target model -> dropped at finalize |

## Multiple managers

Several managers in one application are safe **only when their graphs are
disjoint and never nested**. This is the Django-style setup: each manager owns a
distinct set of kinds, and a router sends each payload to exactly one owner.

```python
# WeatherManager owns the weather graph; BillingManager owns the billing graph.
# No kind appears in both, and no payload embeds a kind from the other.
router = ToolManagerRouter([WeatherManager(), BillingManager()])
```

The rule of thumb:

- **Disjoint + non-nested** graphs -> multiple managers are fine; route by kind.
- **Any overlap or containment** -> merge into a single manager.

A router never stitches a graph together: it picks *one* owner per payload, and
that owner must already contain the whole graph.

## See also

- [Registration](registration.md) — how models and migrations are registered.
- [Execution Flow](execution-flow.md) — discovery, ordering, and finalize.
