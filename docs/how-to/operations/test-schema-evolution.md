# Test schema evolution

The round trip proves that every edge is reachable. The tests on this page prove
that each version still exposes the intended shape and that callable migrations
remain discoverable.

## Prerequisites

- A test manager fixture.
- Registered models and migrations for the topology under test.
- The round-trip test from [Test migrations](test-migrations.md).

## Steps

### Parametrize per version

A whole-chain assertion points at the chain, not the version that drifted. Make
each version a named case and assert the field surface it exposes:

```python
SURFACE = {
    "1.0.0": {"kind", "version", "city", "temperature"},
    "2.0.0": {"kind", "version", "city", "temperature", "humidity"},
    "3.0.0": {"kind", "version", "city", "temperature", "humidity", "wind"},
}


@pytest.mark.parametrize(("version", "surface"), SURFACE.items(), ids=SURFACE)
def test_version_field_surface(manager, version, surface):
    hop = next(
        h for h in walk_topology(manager, kind, versions) if h.version == version
    )
    assert set(hop.payload) == surface
```

Adding a version adds one row; the diff documents the change.

### Test callable migration discoverability

A Python-callable migration executes as-is, but the engine reconstructs missing
models by parsing its source AST. The parser recognizes a narrow set of shapes:

- `return {**data, "field": value}` — addition
- `data["field"] = value` — addition
- `del data["field"]` — removal

Assert discoverability separately from behavior:

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

Write removals as `del data["field"]` (not `del some_copy["field"]`) so the
parser sees them; additions as `{**data, "field": value}`.

### Snapshot a version chain

Snapshot every version's validated dump so a schema change is a visible diff:

```python
def test_all_versions_match_snapshot(manager, snapshot, subtests):
    for node in manager.list_versions(kind):
        version = str(node.version[1])
        with subtests.test(version=version):
            model = manager.adapter.resolve(node.descriptor.ref)
            payload = model(**valid_payload_for(version))
            document = {"container": payload.model_dump(mode="json")}
            assert Doc.model_validate(document).model_dump(mode="json") == snapshot(
                name=version
            )
```

`pytest-subtests` keeps each version a distinct pass/fail; `syrupy` stores the
expected dumps next to the test.

A lighter variant snapshots the field surface per version:

```python
def _field_surface(model: type[BaseModel]) -> dict[str, str]:
    return {n: str(f.annotation) for n, f in sorted(model.model_fields.items())}


@pytest.mark.parametrize("version", ALL_VERSIONS)
def test_version_field_surface_matches_snapshot(manager, version, snapshot):
    model = manager.adapter.resolve(manager.get(kind, version).descriptor.ref)
    assert _field_surface(model) == snapshot(name=f"{kind}@{version}")
```

`pytest --snapshot-update` rewrites only the version whose schema changed.

### Assert hooks and tracing

Hooks are observable. Swap the OTLP exporter for an in-memory one and assert the
spans a migration emits:

```python
def test_one_span_per_step(manager, span_exporter):
    manager.runtime().runner.run(payload, "latest")
    spans = span_exporter.get_finished_spans()
    assert all(s.name.endswith(".migrate") for s in spans)
    assert spans[0].attributes["migration.kind"] == kind
```

## Verify

```bash
pytest tests/test_schema_evolution.py
```

Every version should have a named case, and the snapshot diff should be empty.

## Troubleshooting

- **Snapshot changes for every version:** the sample payload generator drifted;
  fix the generator before updating snapshots.
- **Callable is not discoverable:** rewrite it to one of the recognized AST
  shapes.
- **Missing span:** pass `OtelAdapter` to `manager.runtime(telemetry=...)`.

## See also

- [Test migrations](test-migrations.md) — round-trip topology tests.
- [Property-based tests](property-based-tests.md) — generated payloads and graph
  shapes.
- [Runtime reference → Hooks](../../reference/runtime.md#hooks) — hook contract.
- [Telemetry & hooks](instrument-migrations.md) — instrumentation setup.
