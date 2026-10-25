# Glossary

**Adapter** — provider seam that turns a model or schema into a `VersionNode` and validates payloads. See [Providers](providers.md).

**Backend** — executes a prepared plan. Examples: `ThreadedBackend`, `AsyncBackend`, `ProcessBackend`.

**Command** — normalized registration instruction. `RegisterModel` and `RegisterMigration` are executed by `Engine.register`.

**Convergence** — migrating an entry from its current version to a selected target version.

**Descriptor** — source-level fact emitted during discovery. Model and migration descriptors become registration commands.

**Engine** — build/runtime orchestrator. Owns the registry, adapter, reflector, registration commands, and graph queries.

**Manager** — public bounded-context facade. Configures the engine, exposes registration decorators, and builds runtime runners.

**Migration** — transformation from one adjacent version to the next.

**Registry** — version-graph aggregate. Stores models, migrations, hooks, and graph invariants.

**Runner** — execution facade. Plans a payload, applies target policy and hooks, and delegates to a backend.

**Source** — traversal adapter that emits descriptors for a host system, such as FastMCP or FastStream.

**Target policy** — rule that selects the version each discovered entry converges to.

**Version edge** — adjacent, executable migration between two registered versions.

**Version node** — registered model at one `(kind, version)`.

**Version pair** — source and target endpoints of one migration.
