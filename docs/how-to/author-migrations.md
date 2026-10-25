# Author migrations

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

- [Migrate missing models and migrations](reconstruct-missing-models.md)
- [Migration strategies](../explanation/migrations.md)
- [Migration format reference](../reference/migration-formats.md)
