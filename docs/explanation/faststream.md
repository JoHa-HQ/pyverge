# FastStream Integration

pyverge plugs into [FastStream](https://faststream.airt.ai/) as an adapter: your
subscribers keep declaring FastStream handlers, and pyverge converges each
message body to the policy target before the handler runs — and can converge the
handler's return again on publish.

The adapter lives in `pyverge.adapters.faststream`. pyverge core and its ports
never import FastStream — everything is adapter-local composition over one
`Manager` and one broker.

```bash
pip install "pyverge[faststream]" faststream[kafka]
```

## The model

Nothing new is invented: pyverge converges ordinary payloads, and FastStream
delivers them.

- **Consume seam** — a subscriber registered with `@subscriber(...)` decodes the
  body through a pyverge `decoder`, converging it to the target version. The
  handler's typed parameter names the kind and is bound to the version actually
  served, so validation matches what the handler receives.
- **Produce seam** — a publisher registered with `@publisher(...)` converges the
  handler's return value to an outgoing target before FastStream serializes it.
  The two targets are independent, so a handler can bridge versions across a
  topic boundary.
- **Registration** — models and migrations are registered on the manager
  before the runtime instance is built.

Versioning is pyverge's `(kind, version)` on the payload — the adapter adds no
calling convention of FastStream's own.

## Continue

- [Use FastStream with pyverge](../how-to/integrations/faststream.md)
- [FastStream reference](../reference/faststream.md)
