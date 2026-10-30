# Glossary

**Adapter** — provider seam that turns a model or schema into a `VersionNode` and validates payloads. See [Providers](providers.md).

**Backend** — executes a prepared plan. Examples: `ThreadedBackend`, `AsyncBackend`, `ProcessBackend`.

**Convergence** — migrating an entry from its current version to a selected target version.

**Descriptor** — source-level fact emitted during discovery. Model and migration descriptors are applied through the application registration port.

**Engine** — build/runtime orchestrator. Owns the registry, adapter, reflector, and graph queries. It does not execute registration commands.

**Manager** — public bounded-context facade. Configures the engine, exposes registration decorators, and builds runtime runners.

**Migration** — transformation from one adjacent version to the next.

**Registry** — mutable storage aggregate. Stores node entries, migration bindings, hooks, and indexes. Path resolution belongs to the immutable graph.

**Runner** — execution facade. Plans a payload, applies target policy and hooks, and delegates to a backend.

**Source** — traversal adapter that emits descriptors for a host system, such as FastMCP or FastStream.

**Target policy** — rule that selects the version each discovered entry converges to.

**Version edge** — an `EdgeKey` plus the diff and executable migration binding.

**Node ID** — frozen identity `NodeId(namespace, kind, version)`. The namespace
must match the owning registry.

**Version key** — a `NodeId` plus identity-neutral storage metadata (`ref`).
Equality, ordering, and hashing use the node ID only.

**Version node** — a hydrated `VersionKey` that always binds a `ModelRef` and a
model descriptor.

**Edge key** — a directed `(source NodeId, target NodeId)` pair plus metadata.
Cross-namespace and cross-kind edges are rejected.

**Version pair** — source and target endpoints of one migration.

**Graph snapshot** — immutable `MigrationGraph` built from registry storage. It
contains graph identity, executable-edge identities, and serializable migration
metadata, but no Python callables.

**Hydration** — upgrading a key-only `VersionKey` placeholder to a full
`VersionNode`. Hydration is distinct from reconciliation.

**Key-only entry** — a `VersionKey` or `EdgeKey` that records topology without a
model or executable binding. Key-only entries are valid placeholders but cannot
be executed until hydrated and bound.

**PathFinder** — graph-planning facade that compiles target policy, resolves
migration paths, applies policy, and produces a `PathPlan`.

**GraphBuilder** — compiles registry storage into an immutable `MigrationGraph`
snapshot.

**MigrationDefinition** — executable binding for one edge: diff, callable, and
`MigrationDescriptor`.

**MigrationResolver** — execution-side lookup for migration definitions and
hooks by `EdgeKey`.

**PathFinder** — graph-planning facade that compiles target policy, resolves
paths, applies policy, and returns a `PathPlan`.

**Path plan** — `PathPlan` and `PathPlanEntry`: resolved steps, hooks, callables,
migration descriptors, and target model for each discovered payload entry.

**Graph view** — protocol used by graph consumers. `GraphView` covers models and
migration existence; `PathGraphView` adds `migration_path`.

**Hook state** — backend-provided `ContextVar` used to keep per-step telemetry
state isolated across async tasks and threads.
