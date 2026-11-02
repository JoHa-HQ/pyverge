"""Run the eager demo: ``python -m celery_demo``."""

from __future__ import annotations

import argparse
import json

from .domain import order_v1
from .tasks import TelemetrySettings, build_demo


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Celery multi-version showcase")
    parser.add_argument(
        "--telemetry",
        action="store_true",
        help="Export pyverge run and migration spans over OTLP.",
    )
    parser.add_argument(
        "--otlp-endpoint",
        default="http://localhost:4317",
        help="OTLP gRPC endpoint (default: http://localhost:4317).",
    )
    parser.add_argument(
        "--service-name",
        default="pyverge-celery-demo",
        help="OpenTelemetry service name.",
    )
    return parser


def main() -> None:
    """Run one order through the v1 -> v2 -> v3 chain."""
    args = _parser().parse_args()
    demo = build_demo(
        eager=True,
        telemetry=TelemetrySettings(
            enabled=args.telemetry,
            service_name=args.service_name,
            endpoint=args.otlp_endpoint,
        ),
    )
    try:
        result = demo.run(order_v1())
        print(
            json.dumps(
                {
                    "input": order_v1(),
                    "trace": [
                        {"task": name, "payload": payload}
                        for name, payload in demo.trace
                    ],
                    "result": result,
                },
                indent=2,
                sort_keys=True,
            )
        )
    finally:
        demo.close()


if __name__ == "__main__":
    main()
