# pyverge

[![PyPI version](https://img.shields.io/pypi/v/pyverge.svg)](https://pypi.org/project/pyverge/)
[![PyPI downloads](https://img.shields.io/pypi/dm/pyverge.svg)](https://pypi.org/project/pyverge/)
[![Python versions](https://img.shields.io/pypi/pyversions/pyverge.svg)](https://pypi.org/project/pyverge/)

Schema evolution and migrations for versioned data. Register model versions,
define migrations between them, and converge payloads to a target schema at
runtime. The engine is provider-agnostic; Pydantic and JSON Schema adapters ship
today.

## Installation

```bash
pip install pyverge                 # core library
pip install "pyverge[cli]"          # CLI
pip install "pyverge[fastmcp]"      # MCP tool server
pip install "pyverge[faststream]"   # messaging adapter
```

Development: `uv sync --group dev`.

## Quick start

```python
from typing import Literal

import semver
from pydantic import BaseModel

from pyverge import Manager
from pyverge.migration import MigrationSettings, PydanticModelAdapter

UserManager = Manager[semver.Version].configure(
    MigrationSettings(),
    PydanticModelAdapter(),
)


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


@UserManager.migration("User", "1.0.0", "2.0.0")
def add_age(data: dict, context=None) -> dict:
    return {**data, "age": None}


migrated = UserManager().migrate(
    {"kind": "User", "version": "1.0.0", "name": "Alice", "email": "a@b.com"}
)
# {"kind": "User", "version": "2.0.0", "name": "Alice", "email": "a@b.com", "age": None}
```

### Async and prepared runs

```python
result = await manager.amigrate(payload)

run = manager.delegate(payload)
first = run.run(context={"tenant_id": "tenant_a"})
second = run.run(context={"tenant_id": "tenant_b"})
```

`migrate`/`amigrate` execute immediately. `delegate` and `prepare` return a
reusable `MigrationRun`. Execution policy comes from settings:

```python
MigrationSettings(execution_mode="async", parallel_workers=4)
```

## Migration formats

| Format | Use when | Context |
| --- | --- | --- |
| JSON Patch | structural changes | no |
| JSONata | declarative expressions | yes |
| Python callable | imperative logic | yes |

## CLI

```bash
pyverge init                                       # scaffold project
pyverge doctor --manager myapp.models:UserManager  # registry health
pyverge validate data.json --manager myapp.models:UserManager \
  --schema User --version 1.0.0
pyverge migrate data.json --manager myapp.models:UserManager --target latest
pyverge migrate data.json --manager myapp.models:UserManager --check
pyverge compat --manager myapp.models:UserManager --fail-on-breaking
pyverge manifest --manager myapp.models:UserManager > manifest.json
pyverge diff --manager myapp.models:UserManager --from 1.0.0 --to 2.0.0
pyverge export --manager myapp.models:UserManager
pyverge info --manager myapp.models:UserManager
```

Managers are `module:object_path` and may be an instance, configured subclass,
or zero-arg factory. Runtime schemas require a factory that builds the manager
from their source.

`manifest` is a CLI-only contract: it emits a JGF v2 graph envelope with node
schema hashes, migration hashes, and a content hash. Lifespan/startup does not
write it. CI commands (`doctor`, `validate`, `migrate --check`, `compat`)
return non-zero on failure. Config auto-discovery is not wired yet.

See [CLI Reference](docs/cli.md).

## Features

- **Versioned registry** — semver or ISO date versions, decorator registration
- **Convergent engine** — graph-driven migration of nested versioned entries
- **Declarative migrations** — JSON Patch, JSONata expressions, or Python callables
- **Runtime context** — shared read-only bindings across every step
- **Sync/async executors** — sequential or level-parallel; prepared runs
- **Reflection** — reconstruct missing models or propose migrations from diffs
- **Compatibility** — `CompatibilityReport`, breaking-change checks, JSON Patch rendering
- **Graph manifest** — JGF v2 snapshot with stable hashes for CI divergence checks
- **Adapters** — FastMCP tools/prompts/resources and FastStream messages
- **Hooks** — before/after/error callbacks, async-aware, OpenTelemetry hook

## Documentation

- [Getting Started](docs/getting-started.md)
- [Managers](docs/managers.md) · [Concepts](docs/concepts.md)
- [Migrations](docs/migration.md) · [Migration Formats](docs/migration-formats.md)
- [Runtime & Execution](docs/runtime.md) · [Execution Flow](docs/execution-flow.md)
- [Target Policy](docs/target-policy.md) · [Compatibility](docs/compatibility.md)
- [CLI Reference](docs/cli.md) · [Telemetry & Hooks](docs/telemetry.md)
- [FastMCP](docs/fastmcp.md) · [FastStream](docs/faststream.md)
- [Testing](docs/testing.md) · [Benchmarking](docs/benchmarking.md)
- [Usage Patterns](docs/usage.md) · [Scenarios](docs/scenarios.md)
- [Showcases](showcases/README.md)
