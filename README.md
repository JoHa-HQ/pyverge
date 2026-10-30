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

Every versioned payload you have ever produced is still out there.

Old records in a database. Messages waiting in a queue. A partner integration
that still sends `1.0.0`. A nested customer object inside an order from six
deployments ago. You can change the current schema, but you cannot make every
producer and consumer change at the same moment.

That is the problem pyverge removes.

## The idea

A payload is not one schema. It is a graph of versioned facts.

```text
Order 1.0.0
  └── Customer 2.0.0
        └── Address 1.0.0
```

Each fact has an identity. Each identity can move to a newer version. A
migration is an edge between two identities.

pyverge lets you describe that graph once, then converge any payload to any
target version — including nested entries — without coordinating releases.

The graph separates three things that usually get tangled together:

- **identity** — what version of what kind, in which namespace;
- **schema** — the model that describes a node;
- **execution** — the migration code that moves an edge forward.

That separation is what makes old payloads safe to keep.

## Quick start

### 1. Start with identity

A node is a namespace, a kind, and a version. An edge connects two nodes.

```python
from pyverge.versioning import EdgeKey, NodeId, VersionKey

user_v1 = NodeId.parse("com.acme.users", "User", "1.0.0")
user_v2 = NodeId.parse("com.acme.users", "User", "2.0.0")
user_key = VersionKey.parse("com.acme.users", "User", "1.0.0")
migration_edge = EdgeKey.from_pair(user_v1, user_v2)

assert str(user_v1) == "com.acme.users:User@1.0.0"
assert str(user_key) == "com.acme.users:User@1.0.0"
assert migration_edge.source == user_v1
```

A key is enough to describe topology. It can exist before the model is loaded.

### 2. Hydrate identity with schema

Adapters turn provider models into full version nodes. Storing a key first and
hydrating it later lets discovery, routing, and model loading happen on their
own schedules.

```python
from typing import Literal

from pydantic import BaseModel

from pyverge.registry import Registry
from pyverge.schemas import ModelCodec, PydanticModelAdapter
from pyverge.versioning import VersionKey, default_content_hasher


class UserV1(BaseModel):
    kind: Literal["User"] = "User"
    version: Literal["1.0.0"] = "1.0.0"
    name: str
    email: str


adapter = PydanticModelAdapter(
    codec=ModelCodec(
        namespace="com.acme.users",
        version_property="version",
        kind_property="kind",
    )
)
registry = Registry(
    namespace="com.acme.users",
    hasher=default_content_hasher(),
)
key = VersionKey.parse("com.acme.users", "User", "1.0.0")

registry.store(key)          # topology first
registry.hydrate(adapter.versionable(UserV1))

assert registry.find_model(key) is not None
```

`store()` accepts a key or a full node. `hydrate()` upgrades a key-only
placeholder with a model. `reconcile()` is a separate operation for schema
reconciliation between full nodes. Hydration never invents a model that was
never registered.

### 3. Let the graph answer the question

Once the identities exist, the graph can decide how to get from one version to
another.

```python
from pyverge.graph import GraphBuilder

graph = GraphBuilder().build(registry)

assert graph.get_model(key).model_id.endswith("UserV1")
```

A snapshot may contain key-only and hydrated entries. `EdgeKey` is edge
identity; `VersionEdge` adds the diff and executable migration. Snapshots keep
identity and serializable migration metadata, never Python callables.

Before execution, the graph must prove that the complete selected path is ready:
every node on the path hydrated, every edge bound. A key-only node or unbound
edge forbids execution.

### 4. In practice, use a manager

The manager is the everyday interface. It accepts model classes and decorators,
normalizes them into graph identity, and gives you a runner.

```python
import semver

from pyverge import Manager
from pyverge.schemas import ModelCodec, PydanticModelAdapter


UserManager = Manager[semver.Version].configure(
    PydanticModelAdapter(
        codec=ModelCodec(
            namespace="com.acme.users",
            version_property="version",
            kind_property="kind",
        )
    )
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


manager = UserManager()
migrated = manager.runner().run(
    {"kind": "User", "version": "1.0.0", "name": "Alice", "email": "a@b.com"},
    "latest",
)
# {"kind": "User", "version": "2.0.0", "name": "Alice", "email": "a@b.com", "age": None}
```

The old payload did not need to know that `2.0.0` existed. The new code did not
need to care that the payload was still `1.0.0`.

## Namespaces keep independent worlds apart

Namespace is part of identity, not metadata attached after the fact:

- `NodeId`, `VersionKey`, and `EdgeKey` carry it.
- A graph snapshot is single-namespace.
- Cross-namespace edges are rejected.
- JGF and manifest IDs render as `namespace:kind@version`.
- The adapter codec is the only namespace source.
- `Manager.configure()` derives its registry namespace from the codec.

Use the empty namespace for one application. Use a domain namespace when
multiple packages, tenants, or deployment units can register the same kind and
version.

```python
orders = Manager[semver.Version].configure(
    PydanticModelAdapter(
        codec=ModelCodec(
            namespace="com.acme.orders",
            version_property="version",
            kind_property="kind",
        )
    )
)

billing = Manager[semver.Version].configure(
    PydanticModelAdapter(
        codec=ModelCodec(
            namespace="com.acme.billing",
            version_property="version",
            kind_property="kind",
        )
    )
)
```

Both may register `User@1.0.0`. They remain different identities:
`com.acme.orders:User@1.0.0` and `com.acme.billing:User@1.0.0`.

Namespaces are also what keep references and manifest diffs unambiguous when
graphs are compared across services.

## Migrations are contracts

A migration is not a script hidden in a release note. It is a named edge
between two identities.

| Form | Best for | Runtime context |
| --- | --- | --- |
| JSON Patch | structural changes | no |
| JSONata | declarative transformations | yes |
| Python callable | imperative logic | yes |

Choose the smallest form that expresses the change. The graph treats them the
same way: an edge is executable only when its binding is present.

## Execution without surprises

`Runner.run()` defaults:

```text
container=None
max_depth=-1
context=None
```

Use `context=` for read-only bindings shared across every step:

```python
result = manager.runner().run(
    payload,
    "latest",
    context={"tenant_id": "tenant_99"},
)
```

Async execution uses the same planning path:

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

## In CI

The graph is also a build artifact. The CLI can validate a payload, check
compatibility, or emit a namespace-aware JGF manifest whose content hash changes
only when the graph changes.

```bash
pyverge doctor --manager myapp.models:UserManager
pyverge validate data.json --manager myapp.models:UserManager \
  --schema User --version 1.0.0
pyverge migrate data.json --manager myapp.models:UserManager --target latest
pyverge migrate data.json --manager myapp.models:UserManager --check
pyverge compat --manager myapp.models:UserManager --fail-on-breaking
pyverge manifest --manager myapp.models:UserManager > manifest.json
pyverge info --manager myapp.models:UserManager
```

Managers are `module:object_path` and may be an instance, a configured subclass,
or a zero-arg factory. Runtime schemas require a factory that builds the manager
from their source.

`manifest` is a CLI-only contract. Lifespan/startup does not write it. CI
commands (`doctor`, `validate`, `migrate --check`, `compat`) return non-zero on
failure. Config auto-discovery is not wired yet.

## Installation

```bash
pip install pyverge                 # core library
pip install "pyverge[cli]"          # CLI
pip install "pyverge[fastmcp]"      # MCP tool server
pip install "pyverge[faststream]"   # messaging adapter
```

Development: `uv sync --group dev`.

## Documentation

- [Getting started](docs/tutorials/getting-started.md)
- [Managers](docs/explanation/managers.md) · [Concepts](docs/explanation/concepts.md)
- [Providers](docs/explanation/providers.md)
- [Migrations](docs/explanation/migrations.md) · [Migration formats](docs/reference/migration-formats.md)
- [Runtime and execution](docs/reference/runtime.md) · [Execution flow](docs/explanation/execution-flow.md)
- [Target policy](docs/reference/target-policy.md) · [Compatibility](docs/reference/compatibility.md)
- [API reference](docs/reference/api.md) · [Glossary](docs/explanation/glossary.md)
- [Upgrade guide](docs/reference/upgrades.md)
- [CLI reference](docs/reference/cli.md) · [Telemetry and hooks](docs/how-to/operations/instrument-migrations.md)
- [FastMCP](docs/integrations/fastmcp/index.md) · [FastStream](docs/integrations/faststream/index.md)
- [Testing](docs/how-to/operations/test-migrations.md) · [Benchmarking](docs/how-to/operations/benchmark-adapters.md)
- [Manager API](docs/reference/manager.md) · [Use the manager](docs/how-to/models/use-manager.md)
- [Run payloads](docs/how-to/runtime/run-payloads.md) · [Migrate nested payloads](docs/how-to/runtime/migrate-nested-payloads.md)
- [Scenarios](docs/explanation/scenarios.md)
- [Showcases](showcases/README.md)

## Licensing

This project is licensed under the Apache License 2.0, except for files in the
`tests/` directory, which are licensed separately under the GNU General Public
License v3.0 or later (GPL-3.0-or-later). The root `LICENSE` file applies to
library and runtime code, while `tests/LICENSE` governs the validation suite.

> Upgrading from the previous Manager API? See the
> [upgrade guide](docs/reference/upgrades.md) for `migrate`/`amigrate`,
> `MigrationSettings`, runner, and import-path replacements.

## Security

Do not report security vulnerabilities through public issues. Use
[GitHub private vulnerability reporting](https://github.com/JoHa-HQ/pyverge/security/advisories/new).
See [SECURITY.md](SECURITY.md) for scope, response targets, and disclosure
timeline.
