# Graph Domain Refactor Plan

**Status:** Draft
**Date:** 2026-10-30
**Scope:** `pyverge` graph, registry, execution, discovery, adapters

## 1. Goal

Separate the graph domain from the mutable registry and from payload/execution
concerns.

Target dependency direction:

```text
discovery / CLI / JGF adapters
              ↓
           Manager
              ↓
     execution coordinator
              ↓
         PathFinder
        ↙    ↓     ↘
 graph path  policy  targets
        ↘    ↓     ↙
        MigrationGraph
              ↑
         GraphBuilder
              ↑
      Registry repositories
```

## 2. Decisions

- Version Graph is a core domain.
- Migration Definition is a core domain concept.
- Registry / Repository is infrastructure-facing application storage.
- The runtime graph is immutable and implements only the graph read contract.
- The mutable registry must not pretend to be an immutable graph.
- `NodeRepository` stores `NodeEntry` by `NodeKey`, not by `NodeId`.
- One broad graph interface is kept for now; narrow ports are introduced only
  where they clarify a consumer boundary.
- `PolicyEngine` operates solely on the graph and path plan.
- Target compilation belongs to the graph domain.
- `GraphBuilder` is the bridge between repository storage and the graph domain.
- JGF consumes native graph entries, not the registry.
- Discovery is an inbound adapter and must not be a dependency of the engine.
- Do not add an architecture-test phase.

## 3. Target graph domain

```text
pyverge/graph/
    types.py             graph primitives and graph-domain ports
    graph.py             MigrationGraph
    builder.py           GraphBuilder
    path.py              Path
    path_finder.py       PathFinder facade
    path_resolver.py     PathResolver
    policy.py            PolicyEngine and direction policies
    targets.py           TargetCompiler and target resolvers
    plan.py              PathPlan / PathPlanEntry / graph-level plan
    planner.py           graph-level plan construction
```

## 4. Graph primitives

The graph must speak graph concepts rather than registry/catalog concepts.

```text
GraphNode   = node identity + optional model binding
GraphEdge   = source NodeId + target NodeId + optional executable binding
GraphPath   = ordered graph edges
NodeKey     = repository key for a node entry
```

`MigrationGraph` should expose nodes, edges, paths, migration lookups, and hook
lookups. It should not expose registry-oriented catalog behavior such as
`kind_entries`, broad catalog enumeration, or repository mutation.

`NodeRepository` stores `NodeEntry` by `NodeKey`.

## 5. Migration definitions

Migration definitions are stored in a migration repository keyed by `EdgeKey`.

```text
MigrationDefinition
  edge: EdgeKey
  diff
  migration descriptor
  executable source
```

Stores:

```text
NodeRepository       NodeEntry by NodeKey
MigrationRepository  MigrationDefinition by EdgeKey
HookRepository       hooks by EdgeKey
```

`InMemoryCatalog` may implement all three initially, but they remain separate
conceptual contracts.

For persistence:

- store `MigrationDescriptor` plus the migration artifact;
- resolve executable callables at runtime;
- never serialize Python callables directly.

Phase E separates executable bindings from graph edge identity.  Graph
snapshots contain `EdgeKey` values and serializable migration metadata only.
Execution resolves callables and hooks through `MigrationResolver`
implemented by `MigrationBindings`.

### Functional value of separating migration bindings

- Graph topology becomes independent of executable code.
- Graphs can be exported/imported without callables.
- JGF and a future networkx-backed graph can consume native graph entries.
- Missing or declarative-only migration edges become representable.
- Migration backends can change without changing graph identity.
- Path plans can be cached independently of executable functions.
- Persistence can store only serializable migration descriptors.

## 6. Payload walking vs graph path finding

`CompositeExtractor` is not `PathFinder`.

### Payload walker

Keep payload walking in execution/discovery, conceptually as `PayloadWalker`:

```text
PayloadWalker
  payload + container -> ExtractedEntry(path, node)
```

It is responsible for:

- walking nested dicts and lists;
- identifying versioned entries;
- validating containers;
- returning payload paths.

It is not a graph algorithm.

### PathFinder

`PathFinder` is a graph-domain facade:

```text
PathFinder
  extracted entries + target policy
  -> PathPlan(paths, steps, hooks, migrations)
```

It composes:

- `MigrationGraph`
- `PathResolver`
- `TargetCompiler`
- `PolicyEngine`
- path-plan cache

Execution depends on `PathFinder`, not on the individual graph services.

## 7. Plan split

### Graph-domain plan

```text
PathPlan
PathPlanEntry
  path
  source node
  target node
  steps
  hooks
  migrations
```

Graph-level path planning and plan caching belong to the graph domain.

### Execution-domain plan

```text
ExecutionPlan
  path plan
  payload
  execution levels
```

`ExecutionPlan`, payload binding, backend execution, middleware, and the
execution coordinator remain in execution.

`ExtractedEntry` remains in execution/discovery because it is produced by the
payload walker.

## 8. Policy and target responsibilities

- `TargetCompiler` compiles target policy into a resolver over graph nodes.
- `PolicyEngine` evaluates direction, depth, missing paths, and migration
  existence over the graph and path plan.
- `PathFinder` composes target compilation, path resolution, policy evaluation,
  and plan caching.
- `PolicyEngine` does not compile targets.

## 9. Discovery boundary

Discovery is an inbound adapter:

```text
FastMCP / FastStream / files / HTTP
        -> discovery adapter
        -> application registration port
        -> manager / engine
```

Application services must not import discovery internals.

Current direction is partly reversed because the engine imports discovery
commands. The command layer will be removed later.

## 10. Ports

Keep ports grouped by domain in `types.py` modules.

```text
graph/types.py
    GraphNode
    GraphEdge
    GraphPath
    GraphReadPort
    TargetCatalog
    MigrationResolver
    HookResolver

execution/types.py
    PayloadWalker
    EntryExtractor
    BackendPort
    RuntimePort

schemas/types.py
    ModelIdentityPort
    ModelSchemaPort
    ModelRuntimePort
    ModelReflectionPort
    ModelMaterializationPort

registry/types.py
    NodeRepository
    MigrationRepository
    HookRepository
```

Keep one broad graph interface for now. Split narrower graph ports later only if
a consumer boundary needs one.

## 11. JGF integration

JGF should consume native graph entries:

```text
MigrationGraph -> JGF exporter
JGF importer -> registration port -> manager
```

JGF export requires only:

- nodes;
- edges;
- migration descriptors;
- content addressing data.

It does not need mutable registry behavior.

## 12. Implementation phases

### Phase A — Create the graph domain

- Create `pyverge/graph`.
- Move `Path`, `PathPlan`, `PathPlanEntry`, `PathResolver`, `PolicyEngine`,
  `TargetCompiler`, target resolvers, and graph-level planning.
- Keep `ExecutionPlan`, payload binding, coordinator, runner, backends, and
  middleware in execution.
- Export the new graph-domain surface.

### Phase B — Graph builder

- Add `GraphSnapshotSource`.
- Add `GraphBuilder` in the graph domain.
- `Engine.snapshot()` adapts `InMemoryCatalog` to the snapshot source and calls
  `GraphBuilder`.
- Keep one broad graph interface.

### Phase C — Narrow execution consumers

- Rename `CompositeExtractor` conceptually to `PayloadWalker`.
- Introduce `PathFinder` as the graph-domain facade.
- Execution coordinator depends on `PayloadWalker` + `PathFinder`, not on
  individual graph services.
- Keep executable migration lookup together with graph edges for now.

### Phase D — Split model adapter ports

- `ModelIdentityPort`
- `ModelSchemaPort`
- `ModelRuntimePort`
- `ModelReflectionPort`
- `ModelMaterializationPort`
- Keep `ModelAdapter` as a composition facade.

### Phase E — Migration binding separation

- Move executable migration bindings out of graph edge identity.
- Store `MigrationDefinition` in `MigrationRepository` by `EdgeKey`.
- Keep graph snapshots free of callable objects.
- Resolve executables through `MigrationResolver` at execution time.
- Use native graph entries for JGF export/import.

Implemented as:

- `MigrationGraph` stores `EdgeKey` edges, executable edge identities, and
  serializable migration metadata.
- `GraphBuilder` strips callables and hooks while compiling a snapshot.
- `MigrationDefinition` and `MigrationResolver` are graph-domain ports.
- `MigrationBindings` is the immutable execution-side resolver built from the
  mutable catalog.
- `PathFinder` resolves migration functions and hooks through the resolver.
- `JgfExporter` and `JgfImporter` read and write native graph edge entries.

### Phase F — Remove discovery commands

- Discovery adapters extract entities and call the manager/application
  registration port.
- Remove command types.
- Remove engine → discovery dependency.

Implemented as:

- `pyverge/discovery/commands.py` is removed.
- `MigrationSpec` lives in `pyverge.migrations`.
- Descriptors are applied through `register_descriptor(descriptor, sink)`.
- `RegistrationCollector` collects registrable descriptors directly.
- `Manager` and `FastMCPDiscovery` call the manager registration methods.
- `Reflector` lives in `pyverge.engine`; `discovery.reflection` re-exports it.
- `Engine` has no `pyverge.discovery` imports.

### Phase G — Not needed

No architecture-test phase.

## 13. Non-goals

- No large package reorganization beyond the graph/execution split.
- No narrow read-port split in this pass unless required by a concrete consumer.
- No networkx implementation yet; the graph interfaces should allow it later.
- No command-layer removal before Phase F.

## 14. Acceptance criteria

- `pyverge/graph` owns graph primitives, paths, path finding, policy, targets,
  and graph-level plans.
- Execution owns payload walking, execution plans, coordinator, runner,
  backends, and middleware.
- `PathFinder` is the facade used by execution for graph planning.
- `MigrationGraph` is immutable and speaks graph primitives, not registry
  catalog concepts.
- `GraphBuilder` is the only bridge from repository storage to graph.
- `NodeRepository` stores `NodeEntry` by `NodeKey`.
- Migration definitions are stored by `EdgeKey` in the migration repository.
- JGF consumes native graph entries.
- Discovery adapters depend on application registration ports, not the reverse.
- Model adapter capabilities are split into ports while `ModelAdapter` remains
  the composition facade.
