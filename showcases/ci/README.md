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

## CI checks

- `doctor` fails on missing model references or migration gaps
- `manifest` emits a JGF v2 graph snapshot
- `manifest --baseline manifest.json` compares graph nodes/edges against the
  checked-in snapshot and fails on divergence
- `compat --fail-on-breaking` exits `3` on breaking schema changes
- `migrate --check` fails when the nested payload cannot converge

Update `manifest.json` intentionally when the graph changes:

```bash
pyverge manifest --manager manager:manager --output manifest.json
```

To reuse the workflow in an application repo, copy
`.github/workflows/pyverge.yml` to the repository root and remove
`defaults.run.working-directory`.
