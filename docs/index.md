# pydantic-migrator

Schema evolution and migrations for Pydantic models. Version your models, define migrations between versions, validate/migrate data at runtime, and export schemas to Avro, Protobuf, TypeScript, and JSON Schema.

## Features

- **Versioned model registry** — decorator-based registration with semantic versions
- **Step-wise migrations** — register functions between versions with auto-migration for nested models
- **Batch operations** — streaming batch migrations for large datasets
- **Multi-format schema export** — Avro, Protobuf, TypeScript (interface/type/zod), JSON Schema
- **Model diffing** — breaking change detection, markdown/JSON output
- **Migration hooks** — observability via before/after/error callbacks
- **Migration testing** — input/expected-output test framework with pytest integration
