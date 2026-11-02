# pyverge

Schema evolution and migrations for versioned models.

pyverge converges mixed-version payloads to a target version through a registered
version graph: models, migrations, target policy, and an execution backend.

## Choose a task

| I want to... | Page |
| --- | --- |
| Learn pyverge | [Getting started](tutorials/getting-started.md) |
| Understand identity and hydration | [Graph model and identity](explanation/graph-model.md) |
| Register keys before models | [Keys and hydration](how-to/models/keys-and-hydration.md) |
| Register models | [Register models and migrations](how-to/models/register-models.md) |
| Write a migration | [Author migrations](how-to/migrations/author-migrations.md) |
| Run a payload | [Run payloads](how-to/runtime/run-payloads.md) |
| Reconstruct missing data | [Reconstruct missing models](how-to/migrations/reconstruct-missing-models.md) |
| Use an adapter | [FastMCP](integrations/fastmcp/how-to.md) · [FastStream](integrations/faststream/how-to.md) · [Celery](integrations/celery/how-to.md) · [httpx](integrations/httpx/how-to.md) |
| Upgrade old API | [Upgrade guide](reference/upgrades.md) |

## Start here

- **Learn by doing** — [Getting started](tutorials/getting-started.md)
- **See runnable examples** — [Examples](examples/index.md)
- **Solve a task** — [How-to guides](how-to/index.md)
- **Look up an API** — [Reference](reference/index.md)
- **Understand the model** — [Explanation](explanation/index.md)

## Integrations

- [FastMCP](integrations/fastmcp/index.md) — versioned tools, prompts, resources
- [FastStream](integrations/faststream/index.md) — subscriber/publisher convergence
- [Celery](integrations/celery/index.md) — versioned task payloads and multi-version chains
- [httpx](integrations/httpx/index.md) — client-side request and response convergence

## Contribute

- [Contributing guide](https://github.com/JoHa-HQ/pyverge/blob/main/CONTRIBUTING.md) — code, docs, release process
