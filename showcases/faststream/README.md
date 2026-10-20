# FastStream + pyverge showcase

A runnable pyverge example: versioned message bodies converge to a policy target
**before** a FastStream subscriber handler runs. The same graph and seams run
against any FastStream broker, so the convergence semantics are visible
regardless of transport.

Startup is configured with **Typer**, so the broker is a command-line parameter.

| Kind | Graph |
| --- | --- |
| `Order` | v1 `total` → v2 `+currency` |

## Run

```bash
cd showcases/faststream
uv sync
docker compose up -d --profile kafka   # observability + one broker (see below)
uv run python -m faststream_demo --broker kafka
```

`docker compose up -d` alone starts **Jaeger + an OTLP collector** (always on).
Each broker is under its own Compose profile:

```bash
docker compose up -d --profile kafka      # localhost:9092
docker compose up -d --profile rabbitmq   # amqp://guest:guest@localhost:5672/
docker compose up -d --profile nats       # nats://localhost:4222
docker compose up -d --profile redis      # redis://localhost:6379
```

Then pick the broker per run:

```bash
uv run python -m faststream_demo --broker rabbitmq
uv run python -m faststream_demo --broker nats --target latest
```

A message written at `1.0.0` is handled at `2.0.0` with `currency` filled in.
Open the Jaeger UI at <http://localhost:16686> (service
`pyverge-faststream-demo`) to see the consume span with a `converge.migrate`
child per migration step.

## Microcks (AsyncAPI)

Microcks is the event **source**: two channels, `orders.v1` and `orders.v2`, each
a CloudEvent whose `data` is the explicit model `OrderV1` / `OrderV2`, with a
nested `AddressV1` / `AddressV2`. The envelope is the canonical CloudEvents JSON
Schema (`$ref` to the CloudEvents spec repository). The FastStream app registers
**one handler on both topics** and pyverge converges either `data` to the target.

The contract is separate from configuration: the AsyncAPI file has no broker
URLs. Register the broker endpoints once in Microcks
(Administration → Brokers) using the compose-internal URLs:

| Broker | URL |
| --- | --- |
| Kafka | `kafka:29092` |
| RabbitMQ | `amqp://guest:guest@rabbitmq:5672/` |
| NATS | `nats://nats:4222` |
| Redis | `redis://redis:6379` |

Then run Microcks alongside the matching broker profile and trigger the mock
against that broker:

```bash
docker compose --profile kafka --profile microcks up -d
uv run python -m faststream_demo --broker kafka
```

Open <http://localhost:8080> (no login; Keycloak is disabled). The spec in
`asyncapi/` is mounted at `/deployments/config`; import `orders.yaml` from the
Microcks UI if it isn't picked up automatically.

## Routing

One handler consumes both `orders.v1` and `orders.v2`, converges the inbound body
to `latest`, then routes the payload to version-specific destinations **inside the
handler**:

| Destination | Converged to |
| --- | --- |
| `orders.legacy` | `1.0.0` (drops `currency`) |
| `orders.current` | `2.0.0` |

```python
async def handle_order(event, manager, broker):
    data = event["data"]
    await broker.publish(manager.migrate(data, target="1.0.0"), "orders.legacy")
    await broker.publish(manager.migrate(data, target="2.0.0"), "orders.current")
```

The manager and broker are injected from the FastStream context
(`Context("manager")`, `Context("broker")`). The converged `(kind, version)` is the
routing key; the transport is just dispatch — the same idea an orchestrator uses
to choose an activity/task implementation.

## Parameters

The broker is built with FastStream's own classes (`KafkaBroker` /
`RabbitBroker` / `NatsBroker` / `RedisBroker`) — pyverge adds no abstraction over
brokers. Swapping the broker changes no convergence code.

| Argument / option | Default | Meaning |
| --- | --- | --- |
| `broker` (positional) | — | `kafka` / `rabbitmq` / `nats` / `redis` |
| `dsn` (positional) | — | Connection string (validated per broker) |
| `--topic` | `orders.v1,orders.v2` | Comma-separated input topics |
| `--policy` | `latest` | Convergence target policy |
| `--otlp-endpoint` | `http://localhost:4317` | OTLP collector |
| `--service-name` | `pyverge-faststream-demo` | Span service name |

## Layout

- `cli.py` — the Typer entrypoint (broker, DSN, topics, policy).
- `app/orders/` — the Order feature: anchor model, migrations, the routing
  handler, and the feature wiring.
- `app/infra/` — broker and tracing resources.
- `asyncapi/` — the Microcks AsyncAPI contract.
- `tests/` — offline end-to-end via FastStream's `TestKafkaBroker`.

## Tests

```bash
uv run pytest
```

In-memory broker, no container: the handler sees the converged payload for the
latest and pinned targets.

## Scope

Minimal by design. JSON bodies only, one convergence per message. Batching,
native version negotiation via headers, and per-topic policies are left to a
fuller adapter.
