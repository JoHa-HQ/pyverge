from __future__ import annotations

from typing import Annotated

import typer

from ..config import ConfigError, resolve_manager
from ._shared import ManagerOption, dump_json


def doctor(
    manager: ManagerOption,
    format: Annotated[
        str, typer.Option("--format", help="Output format (text/json)")
    ] = "text",
) -> None:
    try:
        mgr = resolve_manager(manager)
        registry = mgr.registry
        issues = registry.health_issues
        report = {
            "status": "ok" if not issues else "error",
            "kinds": len(registry.entities),
            "versions": len(registry.versions),
            "issues": [issue.message for issue in issues],
            "manager": manager,
        }
        if format == "json":
            dump_json(report)
        else:
            healthy = report["status"] == "ok"
            typer.secho(
                "Registry healthy" if healthy else "Registry issues found",
                fg=typer.colors.GREEN if healthy else typer.colors.RED,
            )
            for issue in report["issues"]:
                typer.echo(f"  - {issue}")
        raise typer.Exit(0 if report["status"] == "ok" else 1)
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1) from exc
