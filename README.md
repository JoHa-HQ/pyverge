# pyverge

Schema evolution and migrations for versioned data models. Version your
models, define migrations between versions, and converge payloads to a target
schema at runtime.

The engine is provider-agnostic: it works on plain dicts and only touches a
model library through the `ModelAdapter` seam. A Pydantic adapter ships today;
adapters for other providers (dataclasses, attrs, marshmallow, MessagePack,
etc.) plug in the same way.

## Installation

```bash
# Core library (versioned registry, migration engine, diffing)
pip install pyverge

# With CLI (init, validate, migrate, diff, export commands)
pip install "pyverge[cli]"

# With OpenTelemetry migration hooks
pip install "pyverge[telemetry]"
```

Development dependencies are managed as a dependency group; install them with
`uv sync --group dev` (or `hatch`/your tool's equivalent).

## Quick Start

```python
from typing import Literal

import semver
from pydantic import BaseModel

from pyverge.migration import (
    MigrationSettings,
    ModelManager,
    PydanticModelAdapter,
)

# A manager binds a version strategy to an adapter and settings.
UserManager = ModelManager[semver.Version].scoped(
    PydanticModelAdapter(),
    settings=MigrationSettings(),
)


# Register versioned models. Version and kind are read from the class itself.
@UserManager.model()
class UserV1(BaseModel):
    kind: Literal["User"] = "User"
    version: Literal["1.0.0"] = "1.0.0"
    name: str
    email: str


@UserManager.model()
class UserV2(BaseModel):
    kind: Literal["User"] = "User"
    version: Literal["2.0.0"] = "2.0.0"
    name: str
    email: str
    age: int | None = None


# Register a migration between two versions.
@UserManager.migration("User", "1.0.0", "2.0.0")
def add_age(data: dict) -> dict:
    return {**data, "age": None}


manager = UserManager()

# Migrate data — converges every versioned entry to the configured target.
migrated = manager.migrate(
    {"kind": "User", "version": "1.0.0", "name": "Alice", "email": "a@b.com"}
)
# -> {"kind": "User", "version": "2.0.0", "name": "Alice", "email": "a@b.com", "age": None}
```

## CLI

```bash
# Requires: pip install "pyverge[cli]"

pyverge init          # Bootstrap a new project
pyverge validate      # Validate data against a schema version
pyverge migrate       # Migrate data between versions
pyverge diff          # Show differences between versions
pyverge export        # Export JSON Schema definitions
pyverge info          # List registered models and versions
pyverge managers      # List available managers from configuration
```

Configuration lives in a `pyverge.toml` (or `[tool.pyverge]` in
`pyproject.toml`), pointing at the module that defines your manager.

## Features

- **Versioned model registry** — decorator-based registration with semver or ISO date versioning
- **Provider adapters** — pluggable `ModelAdapter`; Pydantic ships today, other providers (dataclasses, attrs, marshmallow, MessagePack) plug in the same way
- **Convergent migration engine** — graph-driven, with automatic migration of nested versioned entries
- **Target policies** — converge to `latest`, `earliest`, a pinned version, or per-kind overrides
- **Executors** — sequential or level-parallel batch convergence
- **Model diffing** — breaking-change detection with JSON Patch rendering
- **Migration hooks** — observability via before/after/error callbacks, plus an OpenTelemetry hook

## Documentation

- [Getting Started](docs/getting-started.md)
- [Concepts](docs/concepts.md)
- [Showcases](showcases/README.md)

## Plan

Items intentionally out of scope for this documentation pass, tracked here for
follow-up:

- **CLI/manager facade alignment** — `ModelManager` now exposes `get`,
  `get_latest`, and `list_versions`. The CLI still expects `validate_data`,
  `diff`, `list_models`, `dump_schemas`, and
  `migrate(data, schema, from_version, to_version)` before those commands
  work end-to-end.
- **Additional model providers** — adapters for dataclasses, attrs, marshmallow,
  and MessagePack, mirroring `PydanticModelAdapter` behind the `ModelAdapter`
  seam.
- **Real-source integrations** — `showcases/` projects wiring for document
  storage (converge on read), Kafka consumers, RabbitMQ/streams workers, and
  MQTT/IoT gateways on the high-level `ModelManager` API, with thin adapters
  around real drivers (`motor`, `confluent-kafka`, `aio-pika`, `paho-mqtt`).
  The transport glue is not shipped yet.
- **API reference** — an auto-generated API reference page will be restored
  once the SDK surface is stable.
