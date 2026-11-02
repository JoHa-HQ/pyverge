# Use Celery with pyverge

## Prerequisites

- The Celery adapter installed:

  ```bash
  pip install "pyverge[celery]" celery
  ```

- Models and migrations registered on the manager class.
- A broker for a real worker. Eager mode needs no broker.

## Steps

### Create the shared runtime

```python
import os

from celery import Celery

from pyverge.adapters.celery import CeleryLifecycle, CeleryRuntime

app = Celery("orders", broker=os.environ["CELERY_BROKER_URL"])
runtime = CeleryRuntime(manager)
```

### Register a task

`payload=` names the argument to converge. By default the first parameter is
used.

```python
from pyverge.adapters.celery import task


@task(
    app,
    runtime=runtime,
    target="latest",
    payload="order",
)
def process_order(order: OrderV2) -> OrderV2:
    return order
```

`process_order.delay(order_v1)` executes with a v2 payload.

### Select targets

The target chain is header → task name → queue → default:

```python
@task(
    app,
    runtime=runtime,
    target="latest",
    header="content-version",
    task_targets={"process_legacy": "1.0.0"},
    queue_targets={"legacy": "1.0.0"},
    return_target="1.0.0",
)
def process_order(order: OrderV2) -> OrderV2: ...
```

### Orchestrate tasks across versions

Each task converges its incoming payload to its own target and its result to
`return_target`:

```python
from celery import chain

TARGETS = {"legacy": "1.0.0", "enrich": "2.0.0", "publish": "3.0.0"}


@task(
    app,
    runtime=runtime,
    name="legacy",
    target="latest",
    task_targets=TARGETS,
    return_target="1.0.0",
    payload="order",
)
def legacy(order: OrderV1) -> OrderV1:
    return order


@task(
    app,
    runtime=runtime,
    name="enrich",
    target="latest",
    task_targets=TARGETS,
    return_target="2.0.0",
    payload="order",
)
def enrich(order: OrderV2) -> OrderV2:
    return order


@task(
    app,
    runtime=runtime,
    name="publish",
    target="latest",
    task_targets=TARGETS,
    return_target="3.0.0",
    payload="order",
)
def publish(order: OrderV3) -> OrderV3:
    return order


result = chain(legacy.s(order_v1), enrich.s(), publish.s()).apply_async().get()
```

`legacy` sees v1, `enrich` sees the v1 result converged to v2, and `publish`
sees the v2 result converged to v3.

### Bind the worker lifecycle

`CeleryLifecycle` connects startup and shutdown to Celery's worker signals:

```python
def make_runner():
    return manager.runner()


def close() -> None:
    runtime.runner.backend.close()


CeleryLifecycle(runtime, make_runner, on_shutdown=close).install()
```

The runner factory runs in each worker child, after the fork. Build process
pools, event loops, and exporters there.

### Test in eager mode

Eager mode needs no broker:

```python
app.conf.task_always_eager = True
app.conf.task_eager_propagates = True
result = process_order.delay(order_v1).get()
```

For eager tests, call `lifecycle.startup()` directly or bind the runtime with
`runtime.bind(manager.runner())`.

## Verify

```python
assert result["version"] == "2.0.0"
```

## Troubleshooting

- Handler receives an old version: check the task name, queue, and header
  targets, then confirm the graph has the migration path.
- Import error: install `pyverge[celery]`.
- Worker continues with an unbound runtime: use `CeleryLifecycle`. Celery signal
  dispatch catches ordinary exceptions; the lifecycle converts startup failures
  to `SystemExit`.

## See also

- [Celery integration model](index.md)
- [Celery reference](reference.md)
- [Celery showcase](https://github.com/JoHa-HQ/pyverge/tree/main/showcases/celery)
