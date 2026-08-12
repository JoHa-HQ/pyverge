# Showcases

Real-world patterns for wiring the migration engine into data pipelines. The
examples use the high-level `ModelManager` facade and, where a transport is
involved, wrap a real driver in a thin adapter.

## Data pipelines

- [Event Sourcing](event-sourcing.md) — replaying and upcasting versioned events
- [ETL Pipelines](etl-pipelines.md) — normalizing records from many sources to a warehouse schema
- [Document Storage](document-storage.md) — converge-on-read for a document store (projected)
- [Kafka Consumers](kafka-consumers.md) — converging records in a consumer group (projected)
- [RabbitMQ / Streams Workers](rabbitmq-streams.md) — ack/reject workers for queues and streams (projected)

## Configuration & devices

- [Configuration Management](configuration-management.md) — forward migration and rollback of versioned configs
- [IoT Telemetry](iot-telemetry.md) — converging firmware-specific device payloads
- [MQTT / IoT Streaming](mqtt-iot.md) — converge-and-forward telemetry gateway (projected)

## HTTP APIs & LLM tools

- [HTTP APIs (httpx transport)](http-apis.md) — converging request/response payloads around a versioned API (projected)
- [LLM Tool Schemas (MCP SDK & FastMCP)](llm-tools.md) — converging tool-call arguments across MCP SDK and FastMCP (projected)

## What's glue vs. engine

| Concern | Where it lives |
|---------|----------------|
| Registration and convergence | high-level `ModelManager` facade |
| Target selection | `manager.migrate(..., target=...)` policies |
| Transport (polling, acks, publish, reconnects) | caller glue / driver adapter |
| Offset/DLQ/replay decisions | caller glue |

## Projected integrations

The `(projected)` showcases above illustrate transport wiring that is **not
shipped** — the engine code is real, the driver adapters are illustrative.
