# Testing approach

## Layer the graph

Keep the version graph free of framework imports. Build it without a server, an
adapter, or a collector, then test convergence through the graph and manager
surfaces.

Prefer behavior-level graph tests over internal reassembly. Use `GraphBuilder`,
`PathFinder`, and public registry operations rather than reaching into private
indexes.

## Prefer end-to-end over internal reassembly

Build the application through its composition root and drive it through public
interfaces only. A test that reassembles internal wiring couples itself to the
implementation and breaks on every refactor; a test that calls the public
surface survives it.

The same rule applies to adapters: exercise the public server, broker, task, or
transport surface instead of constructing adapter internals.

## Keep the test suite small

- One convergence suite per adapter.
- One topology round trip per manager.
- Schema-evolution checks for field surfaces and callable discoverability.
- Property-based generation for model contracts and graph shapes.

Reserve unit-style tests for pure layers. If a test needs private attributes or
a reconstructed adapter, move the assertion to a public surface.

## Choose the test

- Round-trip topology: [Test migrations](../how-to/operations/test-migrations.md)
- Field surfaces, callable discoverability, snapshots, hooks:
  [Test schema evolution](../how-to/operations/test-schema-evolution.md)
- Generated payloads and graph shapes:
  [Test with property-based payloads](../how-to/operations/property-based-tests.md)
- Adapter behavior: the adapter's own how-to and showcase.

## See also

- [Test migrations](../how-to/operations/test-migrations.md)
- [Test schema evolution](../how-to/operations/test-schema-evolution.md)
- [Test with property-based payloads](../how-to/operations/property-based-tests.md)
