# Real-World Scenarios

## MCP tool schemas

An LLM tool platform exposes hundreds of tools. Each tool has an input schema
that evolves: a `search_weather` tool gains a `units` parameter, a
`create_ticket` tool renames `assignee` to `owner`. Old tool-call logs persist
at the original schema. New calls arrive at the current schema. When replaying
logs or auditing history, every call must converge to a common version for
analysis.

**Existing approaches:**
- Schema registry with backward-compatible changes only (Avro, Protobuf)
- Manual version branching in tool handlers
- Ad-hoc coercion in the LLM layer

## Message brokers

An event-driven system publishes `OrderCreated` events to Kafka. The event
schema evolves: `price` changes from integer cents to a decimal object,
`items` becomes a nested structure. Consumers must read old events and
interpret them at the current schema. The broker holds a mixed population
across partitions and retention windows.

**Existing approaches:**
- Schema Registry (Confluent) with compatibility rules
- Event upcasting (Axon, EventStoreDB)
- Consumer-side version branching
- Dual-writing during migration windows

## Configuration management

A SaaS app rolls out a new config schema: `feature_flags` becomes a map
instead of a list, `theme` splits into `light_theme` and `dark_theme`. Tenant
configs persist in the database at various versions. On each deployment, old
configs must converge to the current schema without losing data.

**Existing approaches:**
- Migration scripts per tenant (Flyway, Liquibase)
- Default-value coercion at read time
- Versioned config documents with manual reconciliation
- Shadow configs during rollout

## ETL pipelines

A data warehouse ingests records from multiple sources: a legacy CRM at schema
v1, a new API at schema v3, a partner feed at schema v2. The warehouse expects
a uniform schema. Each source record must normalize to the target version
before loading.

**Existing approaches:**
- Source-specific transformers (dbt, Airbyte)
- Staging tables with manual normalization
- Schema-on-read (Delta Lake, Iceberg)
- Custom ETL scripts per source

## IoT telemetry

Sensor gateways buffer telemetry during network outages. When connectivity
returns, the gateway uploads a batch of readings collected over hours. The
cloud schema may have advanced in the meantime: `temperature` gains a `unit`
field, `location` becomes a structured object. The ingestion pipeline must
converge all readings to the current schema for dashboards and alerts.

**Existing approaches:**
- Gateway-side schema embedding (each payload carries its schema)
- Time-windowed schema versions in the pipeline
- Fallback defaults for missing fields
- Replay-only pipelines for historical data
