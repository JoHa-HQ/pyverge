# CI Gate

A nested version graph checked by pyverge in CI.

## Files

- `models.py` — `Person` with an embedded discriminated `Address`
- `migrations.py` — callable migrations for both kinds
- `manager.py` — configured manager exposed as `manager:manager`
- `payloads/person_v1.json` — nested payload at the oldest versions
- `manifest.json` — checked-in JGF v2 graph snapshot
- `.github/workflows/pyverge.yml` — CI gate

## Run locally

```bash
cd showcases/ci
pip install "pyverge[cli]"

pyverge doctor --manager manager:manager
pyverge migrate payloads/person_v1.json --manager manager:manager
pyverge compat --manager manager:manager --fail-on-breaking
pyverge manifest --manager manager:manager \
  --output target/pyverge-manifest.json --baseline manifest.json
```

The payload converges both entries:

- `Address 1.0.0 -> 2.0.0` (child, adds `country`)
- `Person 1.0.0 -> 2.0.0` (parent, adds `email`)

## Graph variants

`variants/` adds additional use-case graphs:

- `chain.py` — three-version chain with forward and reverse migrations;
- `declarative.py` — JSON Patch from v1 to v2 and JSONata from v2 to v3;
- `namespaces.py` — the same `Account@1.0.0` isolated under orders and billing
  namespaces;
- `key_only.py` — a single-namespace graph with key-only placeholders that
  forbids execution until nodes are hydrated and the edge is bound.

Run them with:

```bash
PYTHONPATH=. uv run --project ../.. pytest -q -o addopts= tests
```

The CI job also runs a filtered subset of the official
[JSON Schema Test Suite](https://github.com/json-schema-org/JSON-Schema-Test-Suite)
through `scripts/json_schema_corpus.py`. This exercises adapter materialization
and validation for supported object schemas; it is not a claim of full JSON
Schema validator conformance.

## CI checks

- `doctor` fails on missing model references or migration gaps
- `manifest` emits a JGF v2 graph snapshot
- `manifest --baseline manifest.json` compares graph nodes/edges against the
  checked-in snapshot and fails on divergence
- `compat --fail-on-breaking` exits `3` on breaking schema changes
- `migrate --check` fails when the nested payload cannot converge
- variant graph tests cover chains, declarative migrations, and namespace isolation
- the JSON Schema corpus subset exercises the schema adapter

Update `manifest.json` intentionally when the graph changes:

```bash
pyverge manifest --manager manager:manager --output manifest.json
```

To reuse the workflow in an application repo, copy
`.github/workflows/pyverge.yml` to the repository root and remove
`defaults.run.working-directory`.

## Run the workflow locally

A Docker Compose wrapper runs the real workflow with
[`nektos/act`](https://github.com/nektos/act):

```bash
cd showcases/ci
docker compose run --rm act
```

It mounts the repository root, uses the host Docker socket, and runs
`.github/workflows/pyverge.yml`. The workflow installs the local pyverge
checkout, so it verifies the current source rather than a published release.
