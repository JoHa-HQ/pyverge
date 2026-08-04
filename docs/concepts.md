# Concepts

This page outlines the building blocks of the migration engine and how they
fit together.

## Overview

A migration run has three phases:

1. **Discovery** — walk a payload and find every dict that looks like a
   versioned entry (a registered `(kind, version)` pair).
2. **Planning** — build a dependency graph of those entries, resolve each one
   to a target version, and compute the migration path.
3. **Execution** — apply the migration steps in dependency order (children
   before parents), optionally in parallel.

The `ModelManager` facade wraps all of this; the individual pieces below are
available when you need more control.

## Versions

A version value is either **semver** or an **ISO calendar date**:

- Semver: `1.0.0`, `2.1.0-beta`, `0.1.1.dev7`
- Date: `2024-06-01`, `2025-03-15`

The strategy (semver vs. date) is inferred from the version string. Versions
from different strategies cannot be compared.

### `VersionNode`

Binds a model class, a parsed version value, and a `kind` (the model family,
e.g. `"User"` or `"Address"`). The registry treats `(kind, version)` as a
single comparable unit.

```python
from pyverge.migration import VersionNode

node = VersionNode[object](UserV1, VersionNode.of("1.0.0"), "User")
```

### `SentinelNode`

A lightweight, value-only lookup key — carries just `(kind, version)` with no
model binding. Used to search the registry by version string without building
a full `VersionNode`.

## Migration edges

### `VersionEdge`

A directed edge connecting two versions of the same kind. Carries the `diff`
(between the two model classes) and the migration `func`. Calling the edge
applies the function and wraps failures in a `MigrationError`.

### `SentinelEdge`

A key-only edge sentinel used to look up edges in the registry without
materializing a `Diffable`.

## Registry

The single source of truth for registered models, migrations, and hooks. It
keeps:

- versions in ascending order,
- versions grouped by kind,
- migration edges per kind,
- an inverted index from version → referencing edges,
- hooks per edge.

Register models and migrations through the `Engine` (or the `ModelManager`
facade) rather than directly; the registry validates adjacency and
backward-compatibility rules.

## Model providers

The engine is provider-agnostic: discovery, graph planning, and execution all
operate on plain dicts. The only place a model library is touched is the
`ModelAdapter` seam. `PydanticModelAdapter` ships with the library; adapters
for other providers (dataclasses, attrs, marshmallow, MessagePack, etc.)
implement the same `ModelAdapter` protocol, and the containerless
`CompoundKeyWalker` works with any of them.

## Adapter

`PydanticModelAdapter` is the only place allowed to read `version` and `kind`
off a model class. It follows the idiomatic Pydantic pattern:

```python
class UserV1(BaseModel):
    kind: Literal["User"] = "User"
    version: Literal["1.0.0"] = "1.0.0"
```

It also validates and serializes target models, so the rest of the engine
never touches provider-specific introspection.

## Settings

Settings are layered:

- `VersioningSettings` — `kind_property` and `version_property` names.
- `DiscoverySettings` — adds depth limits and validation mode for payload
  discovery.
- `MigrationSettings` — adds migration behavior: allowed `direction`
  (`forward` / `backward` / `any`), what to do on `on_direction_violation`
  and `on_missing_path` (`skip` / `raise`), `parallel_workers`, and the
  default `target_strategy` (`latest` / `skip`).

## Walkers

Walkers scan a payload for versioned entries.

- `CompoundKeyWalker` — containerless: every dict is checked for a registered
  `(kind, version)` pair. No structural validation. Provider-agnostic.
- `PydanticWalker` — container-driven: validates the payload against a Pydantic
  container model first, then visits fields whose annotations carry
  `BaseModel` subclasses.

## Graph

`GraphBuilder` scans a payload (via a walker) and produces a
`MigrationGraph` of `GraphEntry` objects.

A `GraphEntry` records an entry's `path` in the payload, its `source` version,
resolved `target`, the `steps` between them, and the hooks attached to each
step.

`MigrationGraph` provides:

- `topological_order()` — valid migration order (children before parents),
- `execution_levels()` — independent entries grouped into parallel waves,
- `independent_roots()` — roots of each disjoint connected component.

## Engine

`Engine` orchestrates everything: given a payload and a target policy it
discovers entries, builds the graph, and delegates execution to an executor.
The engine is direction-agnostic and can converge entries forward or backward.

`manager.migrate(data, ...)` on the `ModelManager` facade delegates here.

## Executors

- `StepExecutor` — resolves and runs a single migration step (looks up the
  edge, applies hooks, runs the function, updates the version property).
- `SequentialExecutor` — runs entries one at a time in topological order.
- `LevelParallelExecutor` — runs independent entries within each topological
  level in parallel (thread pool).

## Entry strategies

`EntryMigration` is the per-entry policy: given a `GraphEntry` and its current
data, it decides whether to migrate (direction check), runs the steps, and
finalizes the data against the target model.

`DefaultEntryMigration` is the built-in implementation.

## Target policies

The engine is deliberately agnostic about *what* each entry should converge
to. `compile_target_resolver(registry, policy)` turns a declarative policy
into a resolver:

- `None` or `"skip"` — skip every entry,
- `"latest"` / `"earliest"` — registry extreme for the kind,
- a version string (e.g. `"1.5.0"`) — the registered version for the entry's kind,
- a model class — the registered version of that model,
- a `Versionable` — use as-is,
- a `dict` — per-kind overrides, with `"*"` as the fallback.

```python
from pyverge.migration import compile_target_resolver

resolver = compile_target_resolver(
    registry,
    {"LegacySensor": "1.5.0", "*": "latest"},
)
```

## Diff

`PydanticDiff` computes the differences between two model versions: added,
removed, and modified fields, with queryable predicates (e.g.
`has_type_changes`, `is_added_required`) and pluggable rendering.

`JsonPatchRender` renders the diff as an RFC 6902 JSON Patch.

```python
from pyverge.migration import PydanticDiff

diff = PydanticDiff.from_pair(v1, v2)  # v1, v2 are VersionNode instances
patch = diff.render()                  # JsonPatchRender
```

## Hooks

Hooks are read-only observers fired before, after, and on error for each
migration step.

- `MigrationHook` — base class with no-op defaults; subclass and override
  `before_migrate`, `after_migrate`, and `on_error`.
- `OTELHook` — records each migration as an OpenTelemetry span (requires the
  `telemetry` extra).

## Manager

`ModelManager.scoped(strategy, adapter=..., settings=...)` builds a configured
manager class. Models, migrations, and hooks are registered with the class
decorators `@Manager.model()`, `@Manager.migration(...)`, and `@Manager.hook(...)`
at class level; instantiate the class for the runtime facade.

```python
UserManager = ModelManager.scoped(
    semver.Version,
    adapter=PydanticModelAdapter(),
    settings=MigrationSettings(),
)

@UserManager.model()
class UserV1(BaseModel):
    kind: Literal["User"] = "User"
    version: Literal["1.0.0"] = "1.0.0"
    name: str
    email: str
```

## Exceptions

The module raises typed exceptions for the common failure modes:
`ModelNotFoundError`, `MigrationNotFoundError`, `MigrationAlreadyRegisteredError`,
`ModelAlreadyRegisteredError`, `MigrationError`, `MaxDepthExceededError`, and
`RegistryError`.
