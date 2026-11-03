# Manager API

High-level signatures for the public manager surface. See the
[API reference](api.md) for generated details.

## Configuration

```python
Manager.configure(
    adapter,
    *,
    engine=None,
    hasher=None,
    model_materializer=None,
    migration_materializer=None,
    diff_provider=None,
    on_missing="raise",
    linters=(),
)
```

All configuration is passed directly as keyword arguments. The adapter must
expose a `ModelCodec`; its namespace is the only namespace source for the
manager and registry. There is no fallback namespace and no separate manager
namespace option.

`linters` appends custom `HealthLinter` rules to the registry's defaults, such
as adapter-specific graph invariants. The configured `fail_level` still decides
whether a finding blocks startup.

## Health

```python
Manager.health(entity=None, *, fail_level=None)
```

`fail_level` is a logging-style threshold over `info` < `warning` < `error`;
`"never"` disables blocking. The registry raises `HealthValidationError` when a
finding meets the level.

`ManagerConfig` is deprecated. Pass keywords directly to `Manager.configure`,
or expand `ManagerConfig(...).to_kwargs()` at the call site.

## Registration decorators

```python
@Manager.model()
@Manager.migration(key, ..., backward_compatible=False, migration_id=None)
@Manager.hook(key, hook)
```

## Graph lookup

```python
Manager.get(kind, version)
Manager.get_latest_model(kind)
Manager.list_versions(kind=None)
Manager.get_entities()
Manager.diff(key)
```

## Registration and lifecycle

Registration methods work on the class or on an instance:

```python
Manager.store_model(payload, *, engine=None)
Manager.reconcile_model(payload, *, engine=None)
Manager.store_migration(key, func, *, backward_compatible=False, migration_id=None)
Manager.add_hook(key, hook)
Manager.attach_hooks(hooks)
```

`store_model` accepts a model class, `VersionKey`, or `VersionNode`.
Key-only entries are valid placeholders; `VersionNode` hydrates a matching
placeholder. `reconcile_model` is schema reconciliation, not hydration.

`manager.runtime().graph` returns the immutable graph snapshot owned by the
runtime. Class-level calls update the default engine copied by new instances.
Instance calls update only that instance's engine. Existing instances are not
affected by later class-level registration.

```python
UserManager.add_hook(key, hook)  # affects new instances
manager.add_hook(key, hook)      # affects only this instance
```

## Runtime

```python
manager = Manager()
manager.validate(data, kind, version)
runtime = manager.runtime(
    *,
    runtime=None,
    backend=None,
    middleware=(),
    telemetry=(),
    telemetry_mode="all",
    direction="any",
    on_direction_violation="skip",
    on_missing_path="raise",
    depth_limit=-1,
    on_depth_violation="skip",
    validation_mode="lax",
    discriminator="default",
    plan_cache_size=0,
    copy="deep",
)
runner = runtime.runner
graph = runtime.graph
result = runner.run(
    payload,
    target,
    *,
    source_model=None,
    max_depth=-1,
    context=None,
    validate_target=False,
)
```

See [Use the manager](../how-to/models/use-manager.md) for task examples.
