# Model Wiring Examples

This directory contains examples of different patterns for wiring versioned models with `ModelManager`.

## Registration Patterns

### Class-Level Registration (Preferred)

**Static schema definition** separated from **dynamic runtime configuration**.

```python
# Static: at import time, no instance needed
Manager = ModelManager["UserContainer"]

@Manager.register("1.0.0")
class UserV1(BaseModel): ...

@Manager.register("2.0.0")
class UserV2(BaseModel): ...

@Manager.migration("1.0.0", "2.0.0")
def migrate(data): ...

# Dynamic: at runtime, with configuration
manager = Manager(version_property="version")
manager.migrate(data, "1.0.0", "2.0.0")
```

**Benefits:**
- Clean separation of static schema from runtime config
- No instance needed at import time
- Better for production code where schema is fixed
- Defers instantiation until needed

**See:** `default.py`, `registry.py`

### Instance-Level Registration

Register models and migrations on a manager instance.

```python
# Everything on instance
manager = ModelManager["UserContainer"](version_property="version")

@manager.register("1.0.0")
class UserV1(BaseModel): ...

@manager.register("2.0.0")
class UserV2(BaseModel): ...

manager.migrate(data, "1.0.0", "2.0.0")
```

**Benefits:**
- Isolated registries per instance (good for tests)
- Dynamic registration at runtime
- Backward compatible with older patterns

**See:** `eager.py`, `test_isolation.py`

## When to Use Each

| Scenario | Pattern | Reason |
|----------|---------|--------|
| Production code | **Class-level** | Schema is fixed, defer instantiation |
| Test code | Instance-level | Need isolated registries per test |
| App startup | Class-level | Register once, configure later |
| Dynamic plugins | Instance-level | Register at runtime |
| Library code | Class-level | Users configure via instantiation |


## Example Files

### `default.py` — Class-Level Registration (Preferred)
Static schema definition separated from dynamic runtime configuration. Shows the recommended pattern.

**When to use:**
- Production code
- Single-file models
- When all versions are known upfront

### `eager.py` — Instance-Level Registration
Register models and migrations on a manager instance immediately. Shows many version variants (dev, beta, patch).

**When to use:**
- Test code needing isolated registries
- Dynamic scenarios where registry must be isolated
- Backward compatibility with older code

### `lazy_registration.py` — Deferred Registration
Define all versions first, register them later. Shows both class-level and instance-level patterns.

**When to use:**
- Models defined in one module, registered during app startup
- Separation of concerns
- Cleaner module organization

### `nested_models.py` — Versioned Models in Versioned Models
One versioned model family references another (e.g., `Person` contains `AddressContainer`).

**When to use:**
- Complex domain models with relationships
- Independent versioning of related entities
- Migrations that cascade through nested structures

### `registry.py` — Multiple Manager Coordination
Coordinate multiple `Manager` classes via a `Registry` with shared defaults and batch operations.

**When to use:**
- Domain-driven design with bounded contexts
- Multiple independent versioning streams
- Batch validation, migration testing, and schema dumping

### `test_isolation.py` — Test Isolation
Shows how instance-level registration enables isolated test registries.

**When to use:**
- Test suites with multiple test functions
- Preventing cross-test pollution
- Each test needs its own manager

## Common Structure

All examples follow the same pattern:

1. **Version classes** — Plain `BaseModel` subclasses (e.g., `UserV1`, `UserV2`)
2. **Discriminated union** — `Annotated[UserV1 | UserV2, Field(discriminator="version")]`
3. **Container model** — `BaseModel` wrapping the union (e.g., `UserContainer`)
4. **Manager class** — `ModelManager["UserContainer"]` (class-level) or `ModelManager["UserContainer"]()` (instance-level)
5. **Registration** — `@Manager.register("1.0.0")` (class-level) or `@manager.register("1.0.0")` (instance-level)
6. **Migrations** — `@Manager.migration("1.0.0", "2.0.0")` (class-level) or `@manager.migration("1.0.0", "2.0.0")` (instance-level)
7. **Instantiation** — `Manager(version_property="version")` (class-level only)

## Comparison Table

| Aspect | Class-Level | Instance-Level |
|--------|-------------|----------------|
| **When to register** | Import time | Runtime |
| **Instance needed?** | No | Yes |
| **Isolation** | Shared across instances | Per instance |
| **Best for** | Production code | Test code |
| **Separation of concerns** | Static vs dynamic | All on instance |
| **Backward compatible** | Yes | Yes |

Both patterns are fully supported and can be used together in the same codebase.

## Navigation

Every registered version class gets:
- `VersionClass.version` — String version (e.g., `"1.0.0"`)
- `VersionClass.versioned_model` — `VersionedModel` instance with:
  - `.manager` — Reference back to the `ModelManager`
  - `._container_type` — The container type (e.g., `"UserContainer"`)
  - `.version` — `ModelVersion` object
  - `.name` — Model name string
  - `.load(data)` — Validate and instantiate

This enables navigation from any version class back to its manager and container context, regardless of which registration pattern was used.
