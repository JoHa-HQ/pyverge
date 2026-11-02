# FastStream

pyverge plugs into [FastStream](https://faststream.airt.ai/) as an adapter: your subscribers keep declaring FastStream handlers, and pyverge converges each message body to the policy target before the handler runs — and can converge the handler's return again on publish.

The adapter lives in `pyverge.adapters.faststream`. pyverge core and its ports never import FastStream — everything is adapter-local composition over one `Manager` and one broker.

```bash
pip install "pyverge[faststream]" faststream
```

## The model

Nothing new is invented: pyverge converges ordinary payloads, and FastStream delivers them.

- **Broker facade** — `PyvergeBroker(broker, manager=...)` wraps any FastStream broker once and exposes `subscriber`, `publisher`, and `publish_to` with convergence built in. The facade owns one runtime; pass `runtime=` instead of `manager=` to share one. `broker.underlying` keeps FastStream tooling working.
- **Consume seam** — a subscriber registered with `@broker.subscriber(...)` or `@subscriber(..., runtime=...)` decodes the body through a pyverge `decoder`, converging it to the target version. The runtime owns the manager; direct decorators take the runtime. The handler's typed parameter names the kind and is bound to the version actually served, so validation matches what the handler receives.
- **Produce seam** — a publisher registered with `@broker.publisher(...)` or `@publisher(..., runtime=...)` converges the handler's return value to an outgoing target before FastStream serializes it. The two targets are independent, so a handler can bridge versions across a topic boundary.
- **Registration** — models and migrations are registered on the manager before the runtime instance is built.

Versioning is pyverge's `(kind, version)` on the payload — the adapter adds no calling convention of FastStream's own.

## Worked use cases

The [FastStream showcase](https://github.com/JoHa-HQ/pyverge/tree/main/showcases/faststream)
demonstrates:

- inbound convergence and header negotiation;
- outbound convergence with `publish_to` across multiple routes;
- one handler on multiple input topics;
- target validation at the shared runtime;
- any FastStream broker through one assembly;
- generated AsyncAPI destinations and per-migration OpenTelemetry spans.

Start with its [README](https://github.com/JoHa-HQ/pyverge/blob/main/showcases/faststream/README.md).

## Use it

- [FastStream how-to](how-to.md)
- [FastStream reference](reference.md)
