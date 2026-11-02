# Registry

`Registry` is the in-memory migration-graph aggregate. It owns:

- model and key-only entries;
- migration edges;
- migration registration;
- reflection and binding;
- health linters and cached health issues;
- content-hash indexing.

## Construction

```python
from pyverge.engine import Engine
from pyverge.registry import (
    DEFAULT_HEALTH_LINTERS,
    CompatibilityLinter,
    Registry,
)
from pyverge.versioning import default_content_hasher

registry = Registry(
    namespace="com.acme.orders",
    hasher=default_content_hasher(),
    reflection=reflection,
    linters=(
        *DEFAULT_HEALTH_LINTERS,
        CompatibilityLinter(frozenset({"kind", "version"})),
    ),
    on_missing="raise",
)

engine = Engine(registry, adapter)
```

`namespace` is required and non-empty.

`reflection` is required for migration registration. It is optional for a
storage-only registry.

`linters` is required. Pass `()` to disable health linters explicitly.

## Usage patterns

### Storage-only registry

```python
registry = Registry(
    namespace="com.acme.orders",
    hasher=default_content_hasher(),
    linters=(),
)
```

Use this when only storing entries, reading topology, or importing graph data.
`store_migration(MigrationSpec(...))` fails without `reflection`.

### Build registry

```python
registry = Registry(
    namespace="com.acme.orders",
    hasher=default_content_hasher(),
    reflection=reflection,
    linters=(
        *DEFAULT_HEALTH_LINTERS,
        CompatibilityLinter(frozenset({"kind", "version"})),
    ),
    on_missing="reconstruct_model",
)
```

Use this when registering migrations and reconstructing missing endpoints.

### Manager-owned registry

`Manager.configure(adapter)` builds this configuration automatically from the
adapter codec, reflection stack, default health linters, and `on_missing`
policy. Pass `linters=(...)` to append adapter-specific health rules.

## Model storage

- `store(entry)`
- `hydrate(node)`
- `reconcile(entry)`
- `remove_model(key)`
- `remove_model_by_ref(ref)`
- `clear_models()`

Key-only entries and hydrated nodes share one identity space.

## Migration registration

```python
from pyverge.migrations import MigrationSpec

registry.store_migration(
    MigrationSpec(
        (source_version, target_version),
        migrate,
        backward_compatible=False,
    )
)
```

`store_migration` accepts either a `MigrationSpec` or a direct `EdgeEntry`.
The direct form is used for key-only graph import.

It performs:

- endpoint resolution;
- missing-endpoint reflection when `on_missing="reconstruct_model"`;
- adjacency checks;
- diff construction through `reflection.diff`;
- migration identity resolution from the callable;
- edge storage;
- health refresh.

Reflection and binding are exposed directly as:

- `registry.reflect(anchor, target, migration)` — model materialization;
- `registry.bind(source, target)` — migration binding/proposal.

## Health linters

Linters are callable classes locked per registry instance:

```python
class HealthLinter(Protocol):
    def __call__(
        self,
        catalog: GraphCatalog,
        entity: Identifiable,
    ) -> tuple[HealthIssue, ...]: ...
```

Built-ins:

- `MissingReferencesLinter`
- `MissingEdgeEndpointsLinter`
- `MissingMigrationsLinter`
- `CompatibilityLinter`

`DEFAULT_HEALTH_LINTERS` contains the first three. Add `CompatibilityLinter`
when structural compatibility should be reported. It reports
`migration.structural_breaking` as a `warning`, so it is visible in the health
index without failing a startup policy that raises on `error`.

### Custom linter

```python
from pyverge.registry import DEFAULT_HEALTH_LINTERS, HealthIssue, Registry

class NoDeprecatedKinds:
    def __call__(self, catalog, entity):
        if entity.kind != "Deprecated":
            return ()
        return (
            HealthIssue(
                code="kind.deprecated",
                severity="warning",
                entity=entity,
                message=f"{entity} uses a deprecated kind",
            ),
        )

registry = Registry(
    namespace="com.acme.orders",
    hasher=default_content_hasher(),
    linters=(*DEFAULT_HEALTH_LINTERS, NoDeprecatedKinds()),
)
```

Linters should be immutable or stateless. `copy()` shares the same linter
instances.

### Health lookup

```python
issues = registry.health(node_or_edge)
all_issues = registry.health_issues
```

`health(entity)` is a cached lookup. Linters run during registry mutations, not
on every health read.

Pass `fail_level` to turn the lookup into a startup gate. The threshold follows
logging severity: an issue blocks when its severity is at or above the level.
`"never"` disables the gate.

```python
from pyverge.registry.errors import HealthValidationError

registry.health(node_or_edge, fail_level="error")
registry.health(fail_level="warning")   # every cached entity
```

`HealthValidationError.issues` carries the blocking findings.

Indexes:

```python
registry.issues_by_entity
registry.issues_by_namespace
registry.references_to
```

## Queries

- `versions`, `entries`, `kinds`, `entities`
- `latest`, `earliest`, `latest_version`
- `kind_versions`, `kind_entries`
- `models`, `find_model`, `get_model`, `get_model_by_ref`
- `migrations`, `edges`, `migrations_of`, `edges_of`
- `has_migration`, `get_migration`, `is_adjacent`, `is_critical_edge`

## Copying

`registry.copy()` copies graph state, health indexes, and all immutable
collaborators: reflection, linters, `on_missing`, hasher, namespace, and the
content-hash index setting.
