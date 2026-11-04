# Graph and identity

The graph domain owns identity, immutable snapshots, path planning, target
policy, and graph-level plans. Execution consumes those services.

## Identity

::: pyverge.core.versioning.NodeId

::: pyverge.core.versioning.VersionKey

::: pyverge.core.versioning.EdgeKey

::: pyverge.core.versioning.VersionNode

::: pyverge.core.versioning.VersionEdge

## Snapshots

::: pyverge.core.graph.GraphBuilder

::: pyverge.core.graph.MigrationGraph

## Planning

::: pyverge.core.graph.PathFinder

::: pyverge.core.graph.PathPlan

::: pyverge.core.graph.PathPlanEntry

::: pyverge.core.graph.TargetCompiler

::: pyverge.core.graph.types.GraphView

::: pyverge.core.graph.types.PathGraphView

::: pyverge.core.graph.PolicyEngine

## Boundaries

- A graph snapshot is single-namespace.
- Cross-namespace edges are rejected.
- A key-only entry is a valid placeholder.
- Execution requires the selected path to be fully hydrated and every edge to
  have an executable migration binding.
- `PathPlanEntry.migration_descriptors` exposes strategy and identity for each
  step; callables and descriptors are resolved separately from graph identity.
