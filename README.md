<p align="center">
  <a href="https://pypi.org/project/pyverge/"><img src="https://img.shields.io/pypi/v/pyverge.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/pyverge/"><img src="https://img.shields.io/pypi/dm/pyverge.svg" alt="PyPI downloads"></a>
  <a href="https://pypi.org/project/pyverge/"><img src="https://img.shields.io/pypi/pyversions/pyverge.svg" alt="Python versions"></a>
  <a href="https://scorecard.dev/viewer/?uri=github.com/JoHa-HQ/pyverge"><img src="https://api.scorecard.dev/projects/github.com/JoHa-HQ/pyverge/badge" alt="OpenSSF Scorecard"></a>
</p>

<h1 align="center">pyverge</h1>

<p align="center">
  <strong>Converge versioned payloads to any target schema without coordinated releases.</strong>
</p>

<p align="center">
  <a href="docs/tutorials/getting-started.md">Quick start</a> ·
  <a href="docs/">Docs</a> ·
  <a href="showcases/">Examples</a> ·
  <a href="docs/reference/api.md">API</a>
</p>

## Installation

```bash
pip install pyverge                 # core library
pip install "pyverge[cli]"          # CLI
pip install "pyverge[fastmcp]"      # MCP tool server
pip install "pyverge[faststream]"   # messaging adapter
```

Development: `uv sync --group dev`.

> Upgrading from the previous Manager API? See the
> [upgrade guide](docs/reference/upgrades.md) for `migrate`/`amigrate`,
> `MigrationSettings`, runner, and import-path replacements.

## Quick start

```python
from typing import Literal

import semver
from pydantic import BaseModel

from pyverge import Manager
from pyverge.schemas import PydanticModelAdapter

UserManager = Manager[semver.Version].configure(PydanticModelAdapter())


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


manager = UserManager()
migrated = manager.runner().run(
    {"kind": "User", "version": "1.0.0", "name": "Alice", "email": "a@b.com"},
    "latest",
)
# {"kind": "User", "version": "2.0.0", "name": "Alice", "email": "a@b.com", "age": None}
```

### Async execution

```python
from pyverge.execution import AsyncBackend

runner = manager.runner(
    runtime=AsyncBackend(
        backend="asyncio",
        backend_options={},
        max_workers=4,
    )
)
result = await runner.run(payload, "latest")
```

`Runner.run()` defaults:

```text
container=None
max_depth=-1
context=None
```

Use `context=` for runtime bindings:

```python
result = manager.runner().run(
    payload,
    "latest",
    context={"tenant_id": "tenant_99"},
)
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

See [CLI Reference](docs/reference/cli.md).

## Features

- **Versioned registry** — semver or ISO date versions, decorator registration
- **Convergent engine** — graph-driven migration of nested versioned entries
- **Declarative migrations** — JSON Patch, JSONata expressions, or Python callables
- **Runtime context** — shared read-only bindings across every step
- **Sync/async backends** — threaded, async, or process execution
- **Reflection** — reconstruct missing models or propose migrations from diffs
- **Compatibility** — `CompatibilityReport`, breaking-change checks, JSON Patch rendering
- **Graph manifest** — JGF v2 snapshot with stable hashes for CI divergence checks
- **Adapters** — FastMCP tools/prompts/resources and FastStream messages
- **Hooks** — before/after/error callbacks, async-aware, OpenTelemetry hook

## Security

Do not report security vulnerabilities through public issues. Use
[GitHub private vulnerability reporting](https://github.com/JoHa-HQ/pyverge/security/advisories/new).
See [SECURITY.md](SECURITY.md) for scope, response targets, and disclosure
timeline.

## Documentation

- [Getting started](docs/tutorials/getting-started.md)
- [Managers](docs/explanation/managers.md) · [Concepts](docs/explanation/concepts.md)
- [Providers](docs/explanation/providers.md)
- [Migrations](docs/explanation/migrations.md) · [Migration formats](docs/reference/migration-formats.md)
- [Runtime and execution](docs/reference/runtime.md) · [Execution flow](docs/explanation/execution-flow.md)
- [Target policy](docs/reference/target-policy.md) · [Compatibility](docs/reference/compatibility.md)
- [API reference](docs/reference/api.md) · [Glossary](docs/explanation/glossary.md)
- [Upgrade guide](docs/reference/upgrades.md)
- [CLI reference](docs/reference/cli.md) · [Telemetry and hooks](docs/how-to/telemetry.md)
- [FastMCP](docs/explanation/fastmcp.md) · [FastStream](docs/explanation/faststream.md)
- [Testing](docs/how-to/testing.md) · [Benchmarking](docs/how-to/benchmarking.md)
- [Manager API](docs/reference/manager.md) · [Use the manager](docs/how-to/use-manager.md)
- [Run payloads](docs/how-to/run-payloads.md) · [Migrate nested payloads](docs/how-to/migrate-nested-payloads.md)
- [Scenarios](docs/explanation/scenarios.md)
- [Showcases](showcases/README.md)
