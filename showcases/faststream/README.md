# FastStream + pyverge showcase

A runnable pyverge example: versioned message bodies converge to a policy target
**before** a FastStream subscriber handler runs — and the handler's return can
converge again on publish. The same domain graph and the same seams run against
any FastStream broker, so the convergence semantics are visible regardless of
transport.

FastStream is a broker-agnostic async messaging framework (Kafka, RabbitMQ,
NATS, Redis, MQTT, Confluent). pyverge plugs into its subscriber `decoder`: the
packaged adapter (`pyverge.adapters.faststream`) parses the body, runs it through
a pyverge `Manager`, and hands the handler the target version — binding the
handler's typed payload to the version actually served.

| Kind | Graph |
| --- | --- |
| `Order` | v1 `total` → v2 `+currency` |

## Run

```bash
cd showcases/faststream
uv sync
docker compose up -d --profile kafka   # observability + one broker (see below)
uv run python -m faststream_demo
```

`docker compose up -d` alone starts **Jaeger + an OTLP collector** (always on).
Each broker is under its own Compose profile, so pick one:

```bash
docker compose up -d --profile kafka      # localhost:9092
docker compose up -d --profile rabbitmq   # amqp://guest:guest@localhost:5672/
docker compose up -d --profile nats       # nats://localhost:4222
docker compose up -d --profile redis      # redis://localhost:6379
```

Select the broker the app runs against by name (defaults to `kafka`):

```bash
FASTSTREAM_DEMO__BROKER__NAME=rabbitmq uv run python -m faststream_demo
```

A message written at `1.0.0` is handled at `2.0.0` with `currency` filled in,
whichever broker is running. Open the Jaeger UI at <http://localhost:16686>
(service `pyverge-faststream-demo`) to see the consume span with a
`converge.migrate` child per migration step.

## Broker selection

The broker is chosen from settings and constructed with FastStream's own broker
classes (`KafkaBroker` / `RabbitBroker` / `NatsBroker` / `RedisBroker`) — pyverge
introduces no abstraction over brokers. Swapping the broker changes no
convergence code.

| Setting | Default | Meaning |
| --- | --- | --- |
| `FASTSTREAM_DEMO__BROKER__NAME` | `kafka` | `kafka` / `rabbitmq` / `nats` / `redis` |
| `FASTSTREAM_DEMO__BROKER__SERVERS` | per broker | Connection string |
| `FASTSTREAM_DEMO__BROKER__TARGET` | `latest` | Convergence target policy |
| `TELEMETRY_OTLP_ENDPOINT` | `http://localhost:4317` | OTLP collector |
| `TELEMETRY_SERVICE_NAME` | `pyverge-faststream-demo` | Span service name |
| `TELEMETRY_ENABLED` | `true` | Export spans |

## Layout

- `domain/` — the version graph (anchor model, migration callable, manager).
  No FastStream.
- `adapters/broker.py` — the broker factory (FastStream classes only) and the
  `FastStream` app, wiring the packaged `subscriber` seam and the `Reflector`
  startup hook to the domain manager.
- `adapters/tracing.py` — the OpenTelemetry `TracerProvider` and the per-migration
  hooks; tracing is the host's concern, not the adapter's.
- `settings.py` — env-driven configuration.

## Tests

```bash
uv run pytest
```

Offline end-to-end suite: driven through FastStream's `TestKafkaBroker` (an
in-memory broker — no container), asserting the handler sees the converged
payload for the latest and pinned targets, and that reflection reconciles the
typed handler (including a reconstructed older target).

## Scope

Minimal by design. JSON bodies only, one convergence per message. Batching,
native version negotiation via headers, and per-topic policies are left to a
fuller adapter.
