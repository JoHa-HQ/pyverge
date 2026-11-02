"""Celery worker entrypoint: ``celery -A celery_demo.worker:app worker``."""

from __future__ import annotations

import os

from .tasks import TelemetrySettings, build_demo


def _enabled(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


#: The worker-facing app. The runtime and telemetry bind in
#: ``worker_process_init``, once per child process.
demo = build_demo(
    eager=False,
    telemetry=TelemetrySettings(
        enabled=_enabled(os.getenv("PYVERGE_TELEMETRY", "")),
        service_name=os.getenv("OTEL_SERVICE_NAME", "pyverge-celery-demo"),
        endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"),
    ),
)
app = demo.app

__all__ = ["app", "demo"]
