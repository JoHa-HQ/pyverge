"""Registry health gate for CI."""

from __future__ import annotations

from typing import Annotated, cast

import typer

from pyverge.convergence import CatalogHealth
from pyverge.convergence.catalog.ports import GraphCatalog

from ..config import ConfigError, resolve_manager
from ._shared import ManagerOption, dump_json


def doctor(
    manager: ManagerOption,
    format: Annotated[
        str, typer.Option("--format", help="Output format (text/json)")
    ] = "text",
) -> None:
    """Validate registry health for CI."""
    try:
        mgr = resolve_manager(manager)
        health = CatalogHealth().check(cast("GraphCatalog", mgr.registry))
        report = health.to_dict(manager=manager)
        if format == "json":
            dump_json(report)
        else:
            healthy = report["status"] == "ok"
            typer.secho(
                "Registry healthy" if healthy else "Registry issues found",
                fg=typer.colors.GREEN if healthy else typer.colors.RED,
            )
            for issue in health.issues:
                typer.echo(f"  - {issue}")
        raise typer.Exit(0 if report["status"] == "ok" else 1)
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1) from exc
