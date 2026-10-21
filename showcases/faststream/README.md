# FastStream + pyverge showcase

Versioned message bodies converge to a policy target **before** a FastStream
subscriber runs. One graph, any broker.

`Order`: v1 `total` → v2 `+currency`. Each event is routed to `orders.legacy`
(`1.0.0`) and `orders.current` (`2.0.0`).

## Try it

```bash
cd showcases/faststream
uv sync
export MICROCKS_BROKER_BINDING=KAFKA
export MICROCKS_KAFKA_BOOTSTRAP_SERVER=kafka:29092
docker compose up -d --profile kafka
uv run python -m faststream_demo --microcks kafka kafka://localhost:9092 run
```

`MICROCKS_BROKER_BINDING` and `MICROCKS_KAFKA_BOOTSTRAP_SERVER` are required;
there is no default binding.

A v1 message is handled at v2 with `currency` filled in. Jaeger:
<http://localhost:16686>.

## Brokers

```bash
docker compose up -d --profile kafka      # kafka://localhost:9092
docker compose up -d --profile rabbitmq   # amqp://guest:guest@localhost:5672/
docker compose up -d --profile nats       # nats://localhost:4222
docker compose up -d --profile redis      # redis://localhost:6379
```

```bash
uv run python -m faststream_demo kafka kafka://localhost:9092 run
uv run python -m faststream_demo rabbit amqp://guest:guest@localhost:5672/ run
uv run python -m faststream_demo nats nats://localhost:4222 run
uv run python -m faststream_demo redis redis://localhost:6379 run
```

`--microcks` consumes Microcks-generated destinations
(`Orders-2.0.0-orders.v1` / `.v2`). `--topic`, `--policy`,
`--telemetry/--no-telemetry`, `--service-name`, and `--otlp-endpoint` mirror the
Typer entrypoint; run `--help` for details.

## Use cases

### Subscribe to multiple channels

One handler subscribes to both inputs: `orders.v1` and `orders.v2`.

Start the app and two readers:

```bash
# terminal 1
uv run python -m faststream_demo kafka kafka://localhost:9092 run

# terminal 2
uv run python -m faststream_demo kafka kafka://localhost:9092 \
  read orders.legacy --count 2 --timeout 60

# terminal 3
uv run python -m faststream_demo kafka kafka://localhost:9092 \
  read orders.current --count 2 --timeout 60
```

Send one event on each input:

```bash
# terminal 4
uv run python -m faststream_demo kafka kafka://localhost:9092 \
  send orders.v1 --example v1
uv run python -m faststream_demo kafka kafka://localhost:9092 \
  send orders.v2 --example v2
```

### Publish to multiple channels

Each input event is routed to both outputs after convergence:

| Input | `orders.legacy` | `orders.current` |
| --- | --- | --- |
| v1 | v1, no `currency` | v2, `currency: USD` |
| v2 | v1, no `currency` | v2, `currency: EUR` |

Both readers should receive messages for both sends. `orders.legacy` and
`orders.current` are app-defined output topics; they are not Microcks
destinations.

With `--microcks`, the inputs become `Orders-2.0.0-orders.v1` and
`Orders-2.0.0-orders.v2`; outputs stay the same.

## Send / read

Publish a built-in event and read the converged result:

```bash
uv run python -m faststream_demo kafka kafka://localhost:9092 \
  send Orders-2.0.0-orders.v1 --example v1

uv run python -m faststream_demo kafka kafka://localhost:9092 \
  read orders.legacy --count 1
```

`send` accepts `--example v1|v2`, `--payload '<json>'`, `--file event.json`, and
repeatable `--header key=value`. `read` prints JSON and stops after `--count` or
`--timeout`.

Negotiate a target per message:

```bash
uv run python -m faststream_demo kafka kafka://localhost:9092 \
  send orders.v2 --example v2 --header accept-version=1.0.0
```

The header name is configurable with `--version-header`.

## Tests

```bash
uv run pytest
```

All broker cases run in-memory; select one with `--broker`:

```bash
uv run pytest --broker rabbit
```

Run the full matrix:

```bash
for broker in kafka rabbit nats redis; do
  uv run pytest --broker "$broker"
done
```

For a real broker, use the `send` / `read` commands from [Use cases](#use-cases).

## Microcks

Microcks starts globally; the one-shot `microcks-import` service imports
`asyncapi/orders.yaml` through the REST API using
`MICROCKS_BROKER_BINDING` as the AsyncAPI binding. Open
<http://localhost:8080>. Register broker URLs in Microcks: Kafka `kafka:29092`,
RabbitMQ `amqp://guest:guest@rabbitmq:5672/`, NATS `nats://nats:4222`, Redis
`redis://redis:6379`.

After changing the spec, re-run the importer:

```bash
docker compose run --rm microcks-import
```

## Scope

JSON bodies, one convergence per message. Batching remains out of scope.
Header negotiation and per-topic/per-route targets are supported by the
FastStream adapter.
