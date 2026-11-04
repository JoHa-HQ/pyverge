# Graph and identity

The graph domain owns identity, locked snapshots, path planning, target policy,
revisions, and backend-backed traversal.

## Identity

::: pyverge.core.versioning.NodeId

::: pyverge.core.versioning.VersionKey

::: pyverge.core.versioning.EdgeId

::: pyverge.core.versioning.EdgeKey

::: pyverge.core.versioning.VersionNode

::: pyverge.core.versioning.VersionEdge

Edge identity is:

```text
source + target + discriminator
```

`EdgeId` distinguishes parallel migrations between the same endpoints.
`EdgeKey` adds edge metadata; `VersionEdge` binds hydrated endpoints, a diff, and
a migration descriptor.

## Locks and revisions

::: pyverge.core.graph.MigrationGraph

::: pyverge.core.graph.Revision

::: pyverge.core.graph.RevisionMismatchError

`Engine.snapshot()` is the lock boundary. A snapshot exposes:

```python
graph.revision
graph.content_digest()
graph.manifest_digest()
```

Content digests cover node and edge digests plus hook specs. The manifest digest
includes the revision metadata.

## Backends

::: pyverge.core.graph.GraphBackend

::: pyverge.core.graph.IndexedBackend

::: pyverge.core.graph.RustworkxBackend

::: pyverge.core.graph.IgraphBackend

`IndexedBackend` is the default. `rustworkx` and `igraph` are optional extras.

## Planning

::: pyverge.core.graph.PathFinder

::: pyverge.core.graph.PathPlan

::: pyverge.core.graph.PathPlanEntry

::: pyverge.core.graph.TargetCompiler

::: pyverge.core.graph.GraphView

::: pyverge.core.graph.PathGraphView

::: pyverge.core.graph.PolicyEngine

## Persistence

::: pyverge.core.graph.GraphStore

::: pyverge.core.graph.MemoryGraphStore

::: pyverge.core.graph.PublishedRevision

## Boundaries

- A graph snapshot is single-namespace.
- Cross-namespace edges are rejected.
- A key-only entry is a valid placeholder.
- Execution requires the selected path to be fully hydrated and every edge to
  have an executable migration binding.
- `edge_path()` returns edge identities; `migration_path()` remains a pair-based
  compatibility wrapper.
- Runtime callables and hooks are bound separately from graph identity.
