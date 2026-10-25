# Migrate missing models and migrations

## Reconstructing a model (per migration edge)

A version chain can be represented as declarative patches against a single
latest model — for example, git-versioned JSON specs where only the latest
schema is kept and older versions exist only as patch deltas. Register the
anchor model and the migration; the engine materializes the missing endpoint
model from the anchor and the migration diff.

Enable the strategy in settings:

```python
from pyverge import Manager
from pyverge.providers import PydanticModelAdapter

UserManager = Manager[semver.Version].configure(
    PydanticModelAdapter(),
    on_missing="reconstruct_model",
)
```

Then register only the concrete model you have, plus the migration. The engine
reconstructs every missing version on registration:

```python
# Register the anchor model (the latest concrete schema).
UserManager.store_model(UserV2)

# Register a migration from an unregistered version.
# The engine reconstructs the 1.0.0 model from UserV2 minus the added field.
UserManager.store_migration(
    ("User", "1.0.0", "2.0.0"),
    JsonPatchMigration(
        {
            "from": "1.0.0",
            "to": "2.0.0",
            "ops": [{"op": "add", "path": "/age", "value": None}],
        }
    ),
)

# Runtime instances copy the graph at construction time.
manager = UserManager()

# The 1.0.0 model is now materialized.
v1 = manager.get("User", "1.0.0")
assert v1.model is not None  # fields: kind, version, name
```

When a migration is registered, the engine checks both endpoints against the
registry:

- A **registered** endpoint (with a concrete model) is used as-is.
- An **unregistered** endpoint is reconstructed from the other endpoint's model
  and the migration's diff, then stored in the registry.

The reconstructed model is a real, concrete model — it can be validated
against, introspected, or served with a version-accurate schema. This strategy
**mutates the registry**.

With the default `on_missing="raise"`, registering a migration with an
unregistered endpoint raises `ModelNotFoundError`.

## Reconstructing a migration (per model pair)

The inverse case: you have both concrete models but no migration between them.
Diff the two schemas and render the result as a declarative RFC 6902 spec:

```python
# Both models must be registered (and carry concrete models).
user_v1 = manager.get("User", "1.0.0")
user_v2 = manager.get("User", "2.0.0")

# Diff the two schema versions into a declarative proposal.
proposal = manager.engine.propose_migration(user_v1, user_v2)

# The proposal is a JsonPatchMigration — review it before registering.
UserManager.store_migration(
    ManagerMigrationKey("User", "1.0.0", "2.0.0"), proposal
)
```

The proposal is a **shape-based** diff: it captures field additions, removals
and type changes, but cannot infer business intent (renames, value remaps).
Treat it as a template to edit, never as auto-registered truth.

Unlike model reconstruction, `propose_migration` **never auto-registers** and
**never touches endpoint models** — it returns a proposal you review and
register deliberately.

## Migration formats

Choose the simplest format that expresses the migration:

1. **RFC 6902 JSON Patch** — the portable default. Pure data, no code, easiest
   to serialize, diff, and move between runtimes. Patch ops cannot read runtime
   context; use it for structural changes.
2. **JSONata** — declarative expressions for string formatting, arithmetic,
   filtering, and context-dependent values (`$tenant_id`).
3. **Python callable** — the escape hatch. Full language and full context
   access, but no longer portable configuration.

JSON Patch and callables are normalized into a diff by the engine's discovery
strategies, so reconstruction works the same way regardless of format:

```python
from pyverge.core import ManagerMigrationKey
from pyverge.providers import JsonPatchMigration

# Declarative JSON Patch spec — preferred when no context is needed
UserManager.store_migration(
    ManagerMigrationKey("User", "1.0.0", "2.0.0"),
    JsonPatchMigration(
        {
            "from": "1.0.0",
            "to": "2.0.0",
            "ops": [{"op": "add", "path": "/age", "value": None}],
        }
    ),
)

# Runtime callable — use when the migration needs context or imperative logic
UserManager.store_migration(ManagerMigrationKey("User", "1.0.0", "2.0.0"), add_age)
```

## Runtime context

A migration can read values that are only known when it runs — tenant ids,
request timestamps, exchange rates. Pass them to `migrate`; the same
`MigrationContext` reaches every step:

```python
result = manager.runner().run(payload, "latest", context={"tenant_id": "tenant_99"})
```

The context is a read-only **view** over the mapping you pass, not a copy.
Creation is O(1) and the same instance reaches every step. Do not mutate the
source mapping while a migration is running.

**JSON Patch does not read context.** RFC 6902 has no variables, and keeping it
free of them is what makes it portable. If an op needs a runtime value, promote
that migration to JSONata (declarative + context) or a callable.

Every runtime callable uses the same contract:

```python
from pyverge.core import ManagerMigrationKey

def migrate_v1_to_v2(data, context=None):
    data["tenant_id"] = context["tenant_id"]
    return data

UserManager.store_migration(
    ManagerMigrationKey("User", "1.0.0", "2.0.0"),
    migrate_v1_to_v2,
)
```

`context` is always provided by the engine; the default `None` keeps direct
calls and tests simple.

## Authoring guidelines

### Migrations must be total

A migration for an edge **must map every valid source instance to a valid target
instance**. The engine validates the migrated payload against the target model
and raises if it fails, so a bad edge fails loudly — but the engine cannot know
which source instances exist. Totality is the author's responsibility, not
pyverge's.

The classic trap is a **tightened constraint**: the source allows values the
target forbids. The migration must normalize them, or the source must be
constrained so they never occur.

```python
# v2: age: int | None            (any int)
# v3: age: int = Field(ge=0)     (non-negative)
def migrate_v2_to_v3(data: dict, context=None) -> dict:
    age = data.get("age")
    data["age"] = 0 if age is None else max(age, 0)  # normalize, or…
    data["status"] = "active"
    return data

# …constrain the source so negative ages are invalid at v2 in the first place:
# v2: age: int | None = Field(default=None, ge=0)
```

A `ValidationError` from the **target** model during `migrate` is a symptom of a
non-total edge — fix the migration or the source model, don't widen the target.

### Type the payload shapes

Migrations receive and return plain dicts, but each version has a precise shape.
Document it with `TypedDict`: static-only, no runtime cost, and it keeps the
migration body readable (key access, required keys) while the engine's diff
discovery and reconstruction continue to parse the body.

```python
from typing import Literal, TypedDict, cast


class UserData(TypedDict):
    kind: Literal["User"]
    name: str
    email: str


class UserV1Data(UserData):
    version: Literal["1.0.0"]


class UserV2Data(UserData):
    version: Literal["2.0.0"]
    age: int | None


def add_age(data: UserV1Data, context=None) -> UserV2Data:
    return {**data, "age": None}
```

- `TypedDict` is erased at runtime; migrations still receive and return dicts.
- The engine's diff discovery parses the function body: a returned dict literal,
  or subscript assignments/deletes on the parameter named `data`. Keep that name
  (or return a dict literal) so reconstruction still sees the change.
- A type checker may not prove that a dict-building transform returns the target
  `TypedDict` (for example, when the `Literal` version changes); add a narrow
  `cast` or a targeted ignore where the transform is exact.

### Guard totality with a property test

Generate source instances and assert the edge succeeds. This catches tightened
constraints, required fields the migration forgot, and value remaps that miss a
case:

```python
from hypothesis import given, strategies as st

@given(st.from_type(UserV2))
def test_v2_to_v3_is_total(v2):
    manager.runner().run(v2.model_dump(), target="3.0.0")
```

## Backward migration

Backward migration across a chain works by registering a reverse edge with
`from`/`to` swapped and its own ops:

```python
# Forward edge: 0.1.0 -> 0.2.0
UserManager.store_migration(
    ManagerMigrationKey("User", "0.1.0", "0.2.0"), forward_ops
)

# Reverse edge: 0.2.0 -> 0.1.0 (swapped spec, own ops)
UserManager.store_migration(
    ManagerMigrationKey("User", "0.2.0", "0.1.0"), reverse_ops
)
```

Without a registered reverse edge, a backward migration raises.

## See also

- [Migration strategies](../explanation/migrations.md)
- [Migration format reference](../reference/migration-formats.md)
