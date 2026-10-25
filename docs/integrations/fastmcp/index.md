# FastMCP

pyverge plugs into a [FastMCP](https://github.com/jlowin/fastmcp) server as an adapter: your server keeps declaring FastMCP primitives (tools, prompts, resources), and pyverge reflects each versioned primitive into a version graph, then converges every call's arguments to the policy target before the handler runs.

The adapter lives in `pyverge.adapters.fastmcp`. pyverge core and its ports never import FastMCP — everything here is an adapter-local composition over one `Manager` and one server.

```bash
pip install "pyverge[cli]" fastmcp
```

## The model

Nothing new is invented: pyverge reflects FastMCP primitives into ordinary pyverge models and migrations.

- **Physical primitive** — a FastMCP tool/prompt/resource registered at a `version`. Its reflected `inputSchema` is an *anchor*: the model is registered from it (or reconciled against a hand-registered model).
- **Virtual primitive** — for every other version of that kind, the adapter materializes a primitive whose handler converges arguments to the policy target and then calls the physical anchor. Older callers see the version they declared; the handler always receives the target shape.
- **Convergence** — a versioned call is negotiated natively (FastMCP's `version=`) and routed to the virtual primitive, which converges the payload.

Versioning is FastMCP's, end to end — pyverge adds no calling convention of its own.

## Use it

- [FastMCP how-to](how-to.md)
- [FastMCP reference](reference.md)
