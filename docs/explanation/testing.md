# Testing approach

## Layering for testability

Keep the version graph (domain) free of framework imports. Then tests build the
graph **without** a server, an adapter, or a collector:

```python
manager = build_manager(settings)   # no FastMCP, no OpenTelemetry
for hop in walk_topology(manager, kind, versions):
    ...
```

Define the round-trip helper **locally in the test module** — it is a few lines
and has a single caller, so a separate module would be over-abstraction.

Framework wiring (servers, tracing) lives behind adapters and is exercised by
its own thin suite. Dependency injection keeps the graph construction testable:
wire the version graph as a provider and override it in tests. See
`showcases/fastmcp/` in the repository for a worked layered example with
`dependency-injector`.

## Prefer end-to-end over internal reassembly

Build the application through its **composition root** and drive it through
public interfaces only — the server (`server.call_tool`) and the manager
(`manager.runner().run`). A test that reassembles internal wiring couples itself to
the implementation and breaks on every refactor; a test that calls the public
surface survives it.

```python
@pytest.fixture
async def app(container):
    return await resolve_prepared(container)   # the real lifecycle, once

async def test_call_any_version_converges(app):
    for version in ALL_VERSIONS:               # public call surface
        result = await app.server.call_tool(
            kind, {"city": "Berlin", "version": version}
        )
        assert result.structured_content == expected_anchor_shape
```

Reserve unit-style tests for pure layers (the domain graph), and keep the
end-to-end suite small: one convergence suite plus the topology round trip is
usually enough.
