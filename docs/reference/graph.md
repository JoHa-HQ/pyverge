# Graph and identity

The graph domain owns identity, immutable snapshots, path planning, target
policy, and graph-level plans. Execution consumes those services.

## Identity

::: pyverge.versioning.NodeId

::: pyverge.versioning.VersionKey

::: pyverge.versioning.EdgeKey

::: pyverge.versioning.VersionNode

::: pyverge.versioning.VersionEdge

## Snapshots

::: pyverge.graph.GraphBuilder

::: pyverge.graph.MigrationGraph

## Planning

::: pyverge.graph.PathFinder

::: pyverge.graph.PathPlan

::: pyverge.graph.PathPlanEntry

::: pyverge.graph.TargetCompiler

::: pyverge.graph.PolicyEngine

## Boundaries

- A graph snapshot is single-namespace.
- Cross-namespace edges are rejected.
- A key-only entry is a valid placeholder.
- Execution requires the selected path to be fully hydrated and every edge to
  have an executable migration binding.
