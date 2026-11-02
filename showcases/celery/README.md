# Celery + pyverge showcase

A Celery chain where each task declares a different payload version:

```text
Order v1  ->  ingest (v1)  ->  enrich (v2)  ->  publish (v3)
```

Each task converges its incoming payload to its own target and its return value
to `return_target`, so the chain hands off versions without manual conversion.

## What it demonstrates

| Concern | Where |
| --- | --- |
| Pure version graph | `domain.py` |
| Celery app + shared runtime | `tasks.py` |
| Per-task targets | `@task(..., target="…", return_target="…")` |
| Multi-version orchestration | `chain(ingest.s(...), enrich.s(), publish.s())` |
| Process-isolated migrations | `ProcessBackend(max_workers=2)` |
| Worker lifecycle | `CeleryLifecycle` → `worker_process_init` / `worker_process_shutdown` |
| Worker startup health | `CeleryRuntime.bind(...)` validates the registry per child |
| Telemetry | `OTELHook` per migration + `OtelMiddleware` per run |
| Eager demo and tests | no broker required |

## Architecture

The showcase has one domain boundary and one adapter boundary:

```text
domain.py      Order v1/v2/v3 models, migrations, Manager
tasks.py       Celery app, CeleryRuntime, task decorators, chain
worker.py      Celery CLI entrypoint
__main__.py    eager demo entrypoint
tests/         end-to-end chain tests
```

`domain.py` has no Celery imports. `tasks.py` receives the manager from the
domain and builds one `CeleryRuntime`; the tasks use that runtime. The runtime
owns the runner, context, target validation, health policy, and process backend.

Migrations run in a dedicated `ProcessBackend(max_workers=2)`. In a real worker
the process pool is built in each Celery child process, after the fork, so pools
are never inherited. Hooks stay in the Celery task process, so telemetry is
emitted there while migration callables stay isolated.

Each task declares its own version strategy at decoration time. Adding a task or
a version does not change the runtime or the other tasks.

The `trace` list is a demo/test observability hook. In a real worker, use Celery
signals or structured logs instead.

## Run the eager demo

No broker or worker is required:

```bash
cd showcases/celery
uv sync
uv run python -m celery_demo
```

You should see the v1 input, the payload each task received, and the final v3
result.

## Run a real worker

```bash
cd showcases/celery
docker compose up -d redis
uv run celery -A celery_demo.worker:app worker --loglevel=INFO
```

In another terminal, submit the chain:

```bash
cd showcases/celery
uv run python - <<'PY'
from celery_demo.domain import order_v1
from celery_demo.tasks import build_demo

demo = build_demo(eager=False)
print(demo.run(order_v1()))
PY
```

`build_demo(eager=False)` leaves the runtime unbound in the producer; the task
messages are sent to Redis. `CeleryLifecycle` connects pyverge startup to
`worker_process_init`, so every worker child builds and binds its own runtime,
validates the registry, and closes its process pool in
`worker_process_shutdown`.

Celery signal dispatch catches ordinary exceptions and only logs them. The
lifecycle turns a failed startup into `SystemExit`, so the child stops before it
accepts tasks instead of continuing with an unbound runtime.

Override the defaults with `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND`.

## Telemetry

Start Redis, the OTel collector, and Jaeger:

```bash
cd showcases/celery
docker compose up -d
```

Run the eager demo with telemetry:

```bash
uv run python -m celery_demo --telemetry
```

Open <http://localhost:16686> and select `pyverge-celery-demo`. Each task emits a
`pyverge-celery-demo.run` span and one `pyverge-celery-demo.migrate` child per
migration edge.

For a real worker, opt in per process:

```bash
PYVERGE_TELEMETRY=1   uv run celery -A celery_demo.worker:app worker --loglevel=INFO
```

`TelemetrySettings` is injected into `build_demo`; telemetry is off by default.
`OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_SERVICE_NAME` override the worker
defaults.

## Tests

```bash
cd showcases/celery
uv run pytest
```

The tests use eager mode: `build_demo(eager=True)` binds and validates the
runtime, and `demo.run(...)` drives the public Celery chain. No broker, worker,
or network is required.

## Design notes

- **Single responsibility** — the domain owns models and migrations; the adapter
  owns Celery registration; the entrypoints own process startup.
- **Dependency inversion** — the adapter consumes a manager and a runtime; the
  domain does not import Celery.
- **Open/closed** — new tasks or versions are additive. Existing tasks keep
  their own targets.
- **One runtime** — all tasks share one `CeleryRuntime`, so context, health,
  process isolation, and runner binding are consistent across the chain.
- **Lifecycle ownership** — `CeleryLifecycle` owns signal wiring and fail-fast
  startup; the task definitions and the domain stay lifecycle-free.
- **Injected telemetry** — `TelemetrySettings` is a value object; production can
  disable it, point it at another collector, or replace the provider without
  touching the domain or task definitions.
