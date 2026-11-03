# Test migrations

A version graph has failure modes that per-migration unit tests miss: a missing
reverse edge, a forward migration that is not idempotent, or a finalize step
that silently drops a field.

Use the smallest test that catches the failure:

| Test | Catches |
| --- | --- |
| [Round trip](test-migrations.md#run-the-round-trip) | missing edges and broken hop validation |
| [Schema evolution](test-schema-evolution.md) | drifted field surfaces, callable discoverability, snapshots |
| [Property-based tests](property-based-tests.md) | model-contract and graph-shape regressions |

## Prerequisites

- A test manager fixture.
- Registered models and migrations for the topology under test.
- Reverse edges when the round trip travels backward.

## Steps

### Register the graph in tests

Build the manager through the same factory the application uses, so the test
mirrors production wiring:

```python
@pytest.fixture
def manager():
    return build_manager(settings)  # your domain factory
```

Prefer registering **only the anchor** and letting the engine reconstruct older
versions (`on_missing="reconstruct_model"`). The topology test then also checks
that reconstruction produced the intended schemas.

### Run the round trip

The highest-value test for a version graph is a **round trip**: start from the
newest shape, migrate down to the oldest version, then back up, validating every
hop against its model.

```python
def test_migration_topology(manager, kind, versions):
    newest, oldest = versions[-1], versions[0]
    newest_cls = manager.adapter.resolve(
        manager.get(kind, newest).descriptor.ref
    )

    data = newest_cls.model_validate(
        {"kind": kind, "version": newest, "city": "Berlin"}
    )

    for version in reversed(versions):
        cls = manager.adapter.resolve(manager.get(kind, version).descriptor.ref)
        result = manager.runtime().runner.run(
            data.model_dump(mode="json"), target=version, container=cls
        )
        assert isinstance(result, cls)

    back = manager.runtime().runner.run(
        result.model_dump(mode="json"), target=newest, container=newest_cls
    )
    assert isinstance(back, newest_cls)
```

`container=` validates the migrated payload against the target model, so a
schema mismatch raises instead of passing silently.

### Parametrize over kinds

```python
@pytest.mark.parametrize("kind", ["cv", "jd", "application"])
def test_topology(kind, manager):
    versions = [str(n.version[1]) for n in manager.list_versions(kind)]
    if len(versions) < 2:
        pytest.skip("single version")
    ...  # round trip as above
```

The round trip needs **both directions**. Register reverse edges, or run with
`direction="any"`, before asserting. A forward-only chain should fail:

```python
def test_forward_only_chain_cannot_travel_back(manager):
    with pytest.raises(MigrationNotFoundError):
        walk_down_to_oldest(manager)
```

## Verify

Run the round trip for every registered kind and assert every hop validates.

## Troubleshooting

- **Version mismatch:** the target model differs from the asserted model.
- **Nested entry missing:** register the child kind in the same manager.
- **Down-walk fails:** register the reverse edges or use `direction="any"`.

## See also

- [Test schema evolution](test-schema-evolution.md) — field surfaces, callable
  discoverability, snapshots, and hook assertions.
- [Property-based tests](property-based-tests.md) — generated payloads and graph
  shapes.
- [Execution flow](../../explanation/execution-flow.md) — discovery, ordering, and
  finalize.
- [Migrations](../../explanation/migrations.md) — reconstruct missing models or
  migrations.
- [Telemetry & hooks](instrument-migrations.md) — observability for assertions.
