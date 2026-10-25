# Benchmarking approach

Benchmarks are split by concern: adapter overhead and schema-migration graph
complexity.

## Adapter benchmarks

Measure the integration seam only:

- **FastStream** — publish → decoder convergence → handler, in/out bridge,
  startup source traversal.
- **FastMCP** — primitive traversal and descriptor generation.

Adapter benchmarks keep payloads schema-rigorous: `benchmarks/synthesis.py`
generates instances with Hypothesis, serializes them through the adapter, and
validates each against its source version.

## Schema migration benchmarks

Migration cost grows with graph shape, not only payload size. Measure these
dimensions independently:

| Metric | What it measures | Why it matters |
| --- | --- | --- |
| `versions_per_kind` | Number of model versions registered for one kind. | Increases possible migration edges, path search space, and execution steps. |
| `kinds` | Number of distinct model kinds in one manager or graph. | Increases graph width, registry scans, and cross-kind lookup cost. |
| `migration_path_depth` | Number of migrations traversed from source to target. | Directly multiplies per-run execution, validation, and middleware cost. |
| `fields_per_model` | Number of fields in each model version. | Affects validation, serialization, diffing, and payload transformation cost. |
| `nested_depth` | Depth of container → child → nested-child relationships. | Exercises recursive traversal, extraction, planning, and stack/queue pressure. |
| `payload_entries` | Number of entries inside payloads or containers. | Increases per-entry migration, validation, and serialization work. |

Benchmark shapes:

- **linear chain** — one kind with N adjacent versions
- **wide chain** — many fields per version
- **multi-kind graph** — independent chains in one manager
- **nested graph** — container → children → nested children
- **branching graph** — multiple targets from one source

Measure these workflows:

| Workflow | What it covers |
| --- | --- |
| Registration | model/migration command execution and registry writes |
| Planning | target policy, path resolution, direction, depth |
| Execution | public `Runner.run` end to end |
| Reconstruction | `propose_migration` and missing-model reconstruction |
| Graph export | JGF snapshot and content hashing with larger graphs |

Build graphs outside the timed region. Do not create dynamic Pydantic models
inside benchmark bodies, and do not benchmark private registry internals.

## CLI latency gates

`pyverge benchmark` covers consumer CI checks with in-process `timeit`:

- automatic loop calibration with `timeit.autorange`
- warmup calls
- mean, standard deviation, and percentiles
- JSON reports and baseline comparison

`--iterations` controls timed samples. `--warmup` controls untimed calls.

## Baselines

Adapter suites pair with a plain-framework baseline. Migration suites should pair
against the smallest graph of the same shape, then report the delta across graph
sizes. Track graph size, path depth, and payload shape as benchmark metadata.

## Guardrails

- Fixed synthetic schemas for graph benchmarks.
- Hypothesis-generated payloads for adapter benchmarks.
- No disk or network I/O in timed regions.
- Benchmark public workflows, not implementation details.
- Keep benchmarks out of the default test suite; run explicitly with
  `-o addopts="--benchmark-only"`.

## Running

```bash
# adapter benchmarks
uv run pytest benchmarks/adapters -o addopts="--benchmark-only"

# schema migration graph benchmarks
uv run pytest benchmarks/migrations -o addopts="--benchmark-only"
```
