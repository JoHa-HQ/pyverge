# Concepts

Modern data-driven systems manage a great variety of versioned data. With AI adoption, the evolution these systems have been accelerating at an exponential rate requiring a new approach to versioning of data flowing through the system.

## The problem

### Versioned data evolves

Your application stores structured data. Over time, the schema changes: fields
are added, removed, renamed, or retyped. Old records persist at their original
version. New records arrive at the current version. You end up with a mixed
population:

```
User 1.0.0: { name }
User 2.0.0: { name, email }
User 3.0.0: { name, email, role }
```

### Nested structures compound the problem

Real payloads are not flat. A `User` contains an `Address`. An `Order` contains
`LineItem`s. Each nested piece evolves independently:

```
User 1.0.0 {
  Address 1.0.0 { street, city }
}
```

Later:

```
User 2.0.0 {
  Address 2.0.0 { street, city, country }
}
```

A single payload can contain entries at multiple versions simultaneously.

### Migration is not just transformation

You need to:
- **Discover** every versioned entry in a payload (including deeply nested
  ones).
- **Resolve** what target version each entry should converge to (not always the
  latest).
- **Plan** the migration path (which intermediate versions to traverse).
- **Order** migrations correctly (children before parents).
- **Execute** safely (hooks, error handling, direction checks).
- **Finalize** against the target schema (validation, coercion).

Doing this manually is error-prone. See [real-world scenarios](scenarios.md)
for concrete examples across MCP tools, message brokers, configuration
management, ETL pipelines, and IoT telemetry.

## The solution

### Philosophy

Schema evolution is inevitable. Data persists longer than code. The goal is not
to prevent version drift, but to embrace it: treat every piece of data as
belonging to a versioned family, and provide a systematic way to converge
mixed populations to a desired target.

### The challenge

Across MCP tools, message brokers, configuration management, ETL pipelines, and
IoT telemetry, the same challenges appear:

- **Discovery** — finding every versioned entry in a nested, heterogeneous
  payload without manual enumeration.
- **Target selection** — not every entry should migrate to the latest version;
  some are pinned, some are tenant-specific, some are legacy-only.
- **Ordering** — nested entries must migrate before their parents, but manual
  dependency tracking is error-prone.
- **Execution** — migrations must be safe (hooks, error handling, direction
  checks) and efficient (parallel where possible).
- **Finalization** — migrated data must validate against the target schema.

Existing solutions address pieces of this puzzle but leave gaps: schema
registries enforce compatibility but don't migrate data; event upcasting works
for events but not arbitrary payloads; migration scripts require manual
ordering; ETL transformers are source-specific.

### The pyverge approach

**Convergent migration.** The engine treats each entry independently. Given a
source version and a target version, it finds the registered migration path and
executes it. Entries converge to their targets regardless of where they
started.

**Dependency graph.** Nested entries are dependencies: a parent migration may
assume its children are already at the target version. The engine builds a
graph that captures this containment relationship and migrates in topological
order (children first).

**Policy-driven targets.** Not every entry migrates to the latest version. Some
legacy data is pinned to an older schema. Some tenants are on a different
track. The library accepts a declarative **target policy** and compiles it into
a resolver that answers, for each entry: *"what version should this converge
to?"*

**Provider-agnostic core.** Discovery, planning, and execution operate on plain
dicts. The only place a model library (Pydantic, dataclasses, etc.) is touched
is at the adapter seam. You can swap adapters without changing the engine.

**Meta versions.** A version can be registered by its `(kind, version)` pair
alone, with no concrete model. This lets a version chain be represented as
declarative patches against a single latest model — e.g. git-versioned JSON
specs where only the latest schema is kept. See [meta versions](meta-versions.md).

## Next steps

- [Execution flow](execution-flow.md) — how the engine discovers, plans, and runs migrations.
- [Target policy](target-policy.md) — declarative convergence rules.
- [Meta versions](meta-versions.md) — version chains without concrete models.
- [Real-world scenarios](scenarios.md) — where this applies.
