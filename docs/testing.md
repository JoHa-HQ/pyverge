# Testing

A version graph has failure modes that per-migration unit tests miss: a missing
reverse edge, a forward migration that is not idempotent, or a finalize step
that silently drops a field. This page covers the testing patterns that catch
them.

## Time-travel topology test

The highest-value test for a version graph is a **round trip**: start from a
newest-shaped payload, migrate down to the oldest version, then back up to
newest, asserting every hop yields the correctly-typed container.

```python
def test_migration_topology(manager, kind, versions):
    newest, oldest = versions[-1], versions[0]
    newest_cls = manager.get(kind, newest).model

    data = newest_cls.model_validate(
        {"kind": kind, "version": newest, "city": "Berlin"}
    )

    # Down-walk: newest -> oldest, validating each hop against its model.
    for version in reversed(versions):
        cls = manager.get(kind, version).model
        result = manager.migrate(
            data.model_dump(mode="json"), target=version, container=cls
        )
        assert isinstance(result, cls)

    # Return trip: oldest -> newest.
    back = manager.migrate(
        result.model_dump(mode="json"), target=newest, container=newest_cls
    )
    assert isinstance(back, newest_cls)
```

Why it works: `container=` validates the migrated payload against the target
version's model, so a schema mismatch **raises** instead of passing silently
(silent field drops are the classic bug). It is fully data-driven — parametrize
over every registered kind and run it against your whole registry.

```python
@pytest.mark.parametrize("kind", ["cv", "jd", "application"])
def test_topology(kind, manager):
    versions = [str(n.version[1]) for n in manager.list_versions(kind)]
    if len(versions) < 2:
        pytest.skip("single version")
    ...  # round trip as above
```

### Parametrize per version

A whole-chain assertion points at the chain, not the version that drifted. Make
each version a named case: assert the **field surface** the converged payload
exposes, driven by a table that doubles as documentation of the schema
evolution.

```python
SURFACE = {
    "1.0.0": {"kind", "version", "city", "temperature"},
    "2.0.0": {"kind", "version", "city", "temperature", "humidity"},
    "3.0.0": {"kind", "version", "city", "temperature", "humidity", "wind"},
}

@pytest.mark.parametrize(("version", "surface"), SURFACE.items(), ids=SURFACE)
def test_version_field_surface(manager, version, surface):
    hop = next(h for h in walk_topology(manager, kind, versions) if h.version == version)
    assert set(hop.payload) == surface
```

Adding a version adds one row; the diff documents the change.

The round trip needs **both directions**. Register reverse edges (or run with
`direction="any"`) before asserting, or the down-walk fails with
`MigrationNotFoundError` — which is itself a useful guard test:

```python
def test_forward_only_chain_cannot_travel_back(manager):
    with pytest.raises(MigrationNotFoundError):
        walk_down_to_oldest(manager)
```

## Registering the graph in tests

Build the manager through the same factory the application uses, so the test
mirrors production wiring:

```python
@pytest.fixture
def manager():
    return build_manager(settings)  # your domain factory
```

Prefer registering **only the anchor** and letting the engine reconstruct older
versions (`on_missing="reconstruct_model"`). Then the graph test doubles as a
check that reconstruction produced the intended schemas — assert field presence
per version:

```python
def test_older_models_were_reconstructed(manager):
    v1 = manager.get(kind, "1.0.0")
    assert "wind" not in v1.model.model_fields
```

## Testing callable migrations

A Python-callable migration is executed as-is, but the engine also reconstructs
missing models by **parsing its source AST**. That parser only recognizes a
narrow set of shapes:

- ``return {**data, "field": value}`` → the field is an addition
- ``data["field"] = value`` → addition
- ``del data["field"]`` → removal

A callable written in an unrecognized shape reconstructs the wrong schema
silently. Keep the two concerns apart: assert **discoverability** on the
callable, and assert **behaviour** through the topology walk.

```python
EDGE_EFFECTS = {
    migrations.add_wind: ("wind", None),
    migrations.drop_wind: (None, "wind"),
}

@pytest.mark.parametrize(("func", "effect"), list(EDGE_EFFECTS.items()), ids=...)
def test_callable_is_ast_discoverable(func, effect):
    added, removed = effect
    diff = CallableDiffDiscovery().discover(func, source=meta, target=meta)
    if added:
        assert added in diff.added_fields
    if removed:
        assert removed in diff.removed_fields
```

Write removals as ``del data["field"]`` (not ``del some_copy["field"]``) so the
parser sees them; additions as ``{**data, "field": value}``.

## Property-based payloads

Generate valid payloads for the **latest** model with Hypothesis, then assert
the container validates. This guards the model contract independently of
migrations:

```python
@given(instance=model_strategy(kind))
def test_latest_models(kind, instance):
    Doc.model_validate({"container": instance.model_dump(mode="json")})
```

Compose strategies per nested model and combine them (see joha's
`tests/strategies/` for a worked example). Keep generators aligned with the
model fields — a drifted generator is a false failure, not a real one.

## Snapshotting a version chain

Snapshot every version's validated dump in one parametrized test, so a schema
change is a visible diff rather than a silent break:

```python
def test_all_versions_match_snapshot(manager, snapshot, subtests):
    for node in manager.list_versions(kind):
        version = str(node.version[1])
        with subtests.test(version=version):
            payload = node.model.sample()
            document = {"container": payload.model_dump(mode="json")}
            assert Doc.model_validate(document).model_dump(mode="json") == snapshot(
                name=version
            )
```

`pytest-subtests` keeps each version a distinct pass/fail; `syrupy` stores the
expected dumps next to the test.

A lighter variant snapshots the **field surface** per version — one snapshot
per version, parametrized — which pins the structural evolution of the chain
without depending on sample data:

```python
def _field_surface(model: type[BaseModel]) -> dict[str, str]:
    return {n: str(f.annotation) for n, f in sorted(model.model_fields.items())}


@pytest.mark.parametrize("version", ALL_VERSIONS)
def test_version_field_surface_matches_snapshot(manager, version, snapshot):
    model = manager.get(kind, version).model
    assert _field_surface(model) == snapshot(name=f"{kind}@{version}")
```

`pytest --snapshot-update` then rewrites only the version whose schema changed.

## Asserting on hooks and tracing

Hooks are observable, so assert them directly. Swap the OTLP exporter for an
in-memory one and check the spans a migration emits:

```python
def test_one_span_per_step(manager, span_exporter):
    manager.migrate(payload)
    spans = span_exporter.get_finished_spans()
    assert all(s.name.endswith(".migrate") for s in spans)
    assert span_exporter.get_finished_spans()[0].attributes["migration.kind"] == kind
```

## Layering for testability

Keep the version graph (domain) free of framework imports. Then tests build the
graph **without** a server, an adapter, or a collector:

```python
manager = build_manager(settings)   # no FastMCP, no OpenTelemetry
for hop in walk_topology(manager, kind, versions):
    ...
```

The round-trip helper (`walk_topology`) is a **test utility**, not application
logic — it lives under `tests/` and is imported only by the suite.

Framework wiring (servers, tracing) lives behind adapters and is exercised by
its own thin suite. Dependency injection keeps the graph construction testable:
wire the version graph as a provider and override it in tests. See
`showcases/fastmcp/` in the repository for a worked layered example with
`dependency-injector`.

## See also

- [Execution Flow](execution-flow.md) — discovery, ordering, and finalize.
- [Migrations](migration.md) — reconstruct missing models or migrations.
- [Telemetry & Hooks](telemetry.md) — observability for assertions.
