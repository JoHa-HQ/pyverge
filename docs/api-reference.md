# API Reference

Auto-generated API documentation will be available here using `mkdocstrings`.

## Core Classes

- `ModelManager` — High-level interface for versioned model management
- `Registry` — Model registry for versioned Pydantic models
- `MigrationManager` — Migration execution engine
- `ModelVersion` — Semantic version representation

## Schema Generators

- `SchemaManager` — JSON schema generation
- `AvroSchemaGenerator` — Avro schema generation
- `ProtoSchemaGenerator` — Protocol Buffer schema generation
- `TypeScriptSchemaGenerator` — TypeScript schema generation

## Hooks

- `MigrationHook` — Base class for migration hooks
- `MetricsHook` — Built-in metrics collection

## Testing

- `MigrationTestCase` — Test case definition
- `MigrationTestResults` — Test results aggregation

---

> Configure `mkdocstrings` in `mkdocs.yml` to auto-gerate this page from docstrings.
