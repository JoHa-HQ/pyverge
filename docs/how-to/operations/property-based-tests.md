# Test with property-based payloads

Property-based tests generate valid payloads and graph shapes instead of
enumerating examples by hand. They catch model-contract drift and graph-shape
regressions that fixed fixtures miss.

## Prerequisites

- A test manager fixture.
- Registered models and migrations.
- `hypothesis` installed.

## Steps

### Generate payloads for the latest model

Generate valid payloads for the **latest** model, then assert the container
validates. This guards the model contract independently of migrations:

```python
@given(instance=model_strategy(kind))
def test_latest_models(kind, instance):
    Doc.model_validate({"container": instance.model_dump(mode="json")})
```

Compose strategies per nested model and combine them. See the repository's
`tests/strategies/` for a worked example. Keep generators aligned with the model
fields — a drifted generator is a false failure, not a real one.

### Guard migration totality

Generate source instances and assert the edge succeeds. This catches tightened
constraints, required fields the migration forgot, and value remaps that miss a
case:

```python
from hypothesis import given, strategies as st

@given(st.from_type(UserV2))
def test_v2_to_v3_is_total(v2):
    manager.runtime().runner.run(v2.model_dump(), target="3.0.0")
```

### Generate graph shapes

Use Hypothesis for topology combinations: namespace, node count, hydration, and
edge connectivity. Assert observable path behavior only.

```python
@pytest.mark.parametrize("nodes", [[UserV1, UserV2]], indirect=True)
def test_graph_path(graph, nodes):
    assert graph().migration_path(nodes[0], nodes[1]) == [(nodes[0], nodes[1])]
```

The graph suite is split by concern:

- `test_identity.py` — `NodeId`, `VersionKey`, `EdgeKey`, digests;
- `test_builder.py` — snapshot construction and key-only entries;
- `test_paths.py` — complete-path hydration and binding;
- `test_planning.py` — `PathFinder`, target policy, policy engine;
- `test_synthetic.py` — Hypothesis-generated graph shapes.

Prefer behavior-level assertions through the public graph API. Reuse the shared
`registry`, `graph`, `nodes`, and `path_finder` fixtures instead of rebuilding
adapters in each test.

### Keep generators honest

- Generate only values the model accepts.
- Derive version-specific payloads from the model, not from a hand-written
  dictionary.
- Keep the latest-model generator independent of migration logic.
- Use shrinking to turn a failure into a minimal payload.

## Verify

```bash
pytest tests/test_synthetic.py tests/test_models.py
```

A failure should shrink to a minimal payload or graph shape that reproduces it.

## Troubleshooting

- **Hypothesis reports an invalid example:** the generator produced data the
  model rejects; fix the strategy, not the model.
- **A migration test fails only for generated data:** check totality and
  tightened constraints in the migration.
- **Generated graph is valid but planning fails:** assert the path through the
  public graph API and inspect hydration/binding.

## See also

- [Test migrations](test-migrations.md) — round-trip topology tests.
- [Test schema evolution](test-schema-evolution.md) — field surfaces, callable
  discoverability, and snapshots.
- [Testing approach](../../explanation/testing.md) — layering and test budget.
