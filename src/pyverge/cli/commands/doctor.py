"""Registry health gate for CI."""

from __future__ import annotations

from itertools import pairwise
from typing import Annotated

import typer

from pyverge.core import MissingReferenceError, SentinelEdge

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
        issues: list[str] = []

        try:
            mgr.engine.validate()
        except MissingReferenceError as exc:
            issues.append(str(exc))

        registry = mgr.registry
        for kind in registry.entities:
            versions = registry.kind_versions(kind)
            for source, target in pairwise(versions):
                if not registry.has_migration(SentinelEdge.from_pair(source, target)):
                    issues.append(
                        f"{kind}: missing migration "
                        f"{source.version[1]} -> {target.version[1]}"
                    )

        report = {
            "status": "ok" if not issues else "error",
            "manager": manager,
            "kinds": len(registry.entities),
            "versions": len(registry.versions),
            "issues": issues,
        }
        if format == "json":
            dump_json(report)
        else:
            typer.secho(
                "Registry healthy" if not issues else "Registry issues found",
                fg=typer.colors.GREEN if not issues else typer.colors.RED,
            )
            for issue in issues:
                typer.echo(f"  - {issue}")
        raise typer.Exit(0 if not issues else 1)
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1) from exc
