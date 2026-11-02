# Celery reference

## `task(app, *, runtime, target="latest", return_target=None, header="content-version", task_targets=None, queue_targets=None, payload=None, **options)`

Registers a Celery task whose payload and return value converge. The task
uses `runtime.manager`; the runtime is the single source for the manager,
runner, context, and health policy.

- `target` — default target policy.
- `return_target` — result target; defaults to `target`.
- `header` — negotiation header.
- `task_targets` / `queue_targets` — per-name/per-queue policies.
- `payload` — payload parameter name; defaults to the first parameter.
- `options` — passed to `app.task`.

## `CeleryRuntime`

Shares `ConvergenceRuntime`: runner binding, context, `converge`, health, and
target validation.

`runtime.bind(runner)` validates registry health and raises Celery's
`CeleryError` on failure. Pass `validate_health=False` when binding before all
models are registered, then call `runtime.validate_health()`.

`context_factory=lambda request: MigrationContext.create({...})` maps the
Celery request (id, headers, retries, hostname) to migration context.

The task decorator takes the shared runtime:

```python
runtime = CeleryRuntime(manager)

@task(app, runtime=runtime, target="latest", payload="order")
def process_order(order: OrderV2) -> OrderV2: ...
```

## `CeleryLifecycle(runtime, runner_factory, *, validate_health=True, on_shutdown=None)`

Connects pyverge lifecycle work to Celery worker signals.

`install()` connects:

- `worker_process_init` → `startup()`
- `worker_process_shutdown` → `shutdown()`

`startup()` calls `runner_factory()`, binds the runner to the runtime, and
validates registry health. It raises `CeleryError` on failure.

The signal receiver converts startup failures to `SystemExit`. Celery signal
dispatch catches and logs ordinary exceptions, so raising `CeleryError` there
would leave the worker alive with an unbound runtime.

`shutdown()` calls `on_shutdown` when supplied. Use it to close process pools,
event loops, and telemetry providers created by the runner factory.

`uninstall()` disconnects both receivers. Call `startup()` and `shutdown()`
directly for eager mode or tests.
