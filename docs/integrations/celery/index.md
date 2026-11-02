# Celery

pyverge converges Celery task payloads before the task body runs, and converges
the return value before Celery stores it in the result backend.

```bash
pip install "pyverge[celery]" celery
```

## The model

Celery delivers tasks; pyverge converges the payload at the task boundary.

- **Consume seam** — `@task(...)` converges the payload argument to the selected
  target.
- **Produce seam** — the task return is dumped and converged before the result
  backend.
- **Targets** — header, task name, queue, or a default policy.
- **Lifecycle** — `CeleryLifecycle` binds a runner and validates registry health
  in each worker process.
- **Runtime** — all tasks share one `CeleryRuntime`; the runtime owns the
  manager, runner, context, target validation, and health policy.

`process_order.delay(order_v1)` executes with a v2 payload when the task target
is v2.

## When to use it

Use the Celery adapter when:

- tasks receive versioned payloads from older producers;
- a task chain hands payloads between different schema versions;
- a worker should validate the graph before accepting tasks.

For synchronous task execution in tests, Celery's eager mode needs no broker.

## Use it

- [Celery how-to](how-to.md)
- [Celery reference](reference.md)
- [Celery showcase](https://github.com/JoHa-HQ/pyverge/tree/main/showcases/celery)
