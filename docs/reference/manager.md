# Manager API

High-level signatures for the public manager surface. See the
[API reference](api.md) for generated details.

## Configuration

```python
Manager.configure(adapter, *, config=None, **options)
```

`ManagerConfig` groups optional engine, walker, hasher, identity resolver,
materializer, diff provider, and `on_missing` settings.

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

Class-level calls update the default engine copied by new instances. Instance
calls update only that instance's engine. Existing instances are not affected by
later class-level registration.

```python
UserManager.add_hook(key, hook)  # affects new instances
manager.add_hook(key, hook)      # affects only this instance
```

## Runtime

```python
manager = Manager()
manager.validate(data, kind, version)
runner = manager.runner(
    *,
    runtime=None,
    direction="any",
    on_direction_violation="skip",
    on_missing_path="raise",
    depth_limit=-1,
    on_depth_violation="skip",
    validation_mode="lax",
)
result = runner.run(payload, target, *, container=None, max_depth=-1, context=None)
```

See [Use the manager](../how-to/models/use-manager.md) for task examples.
