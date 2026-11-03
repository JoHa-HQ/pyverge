from __future__ import annotations

import importlib
from dataclasses import asdict
from typing import Annotated, Any

import typer

from pyverge.runtime.manager.discovery import DiscoveryService

from ..config import ConfigError, resolve_manager
from ._shared import ManagerOption, dump_json


def discover(
    source: Annotated[
        str,
        typer.Argument(help="Source import path (module:object_path)"),
    ],
    manager: ManagerOption,
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Register discovered models and migrations"),
    ] = False,
    format: Annotated[
        str, typer.Option("--format", help="Output format (text/json)")
    ] = "text",
) -> None:
    try:
        if ":" not in source:
            raise ConfigError(
                f"Source spec must be 'module:object_path', got '{source}'"
            )
        module_path, object_path = source.split(":", 1)
        obj: Any = importlib.import_module(module_path)
        for part in object_path.split("."):
            obj = getattr(obj, part)
        if callable(obj) and not hasattr(obj, "accept"):
            obj = obj()

        manager_instance = resolve_manager(manager)
        service = DiscoveryService()
        collector = service.collect(obj)
        report = (
            service.apply(collector, manager_instance)
            if apply
            else service.report(collector)
        )

        if format == "json":
            dump_json(asdict(report))
        else:
            typer.echo(f"source: {report.source_id}")
            typer.echo(f"descriptors: {report.descriptors}")
            typer.echo(f"registered models: {report.registered_models}")
            typer.echo(f"registered migrations: {report.registered_migrations}")
            if report.skipped:
                typer.echo(f"skipped: {', '.join(report.skipped)}")
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1) from exc
    except typer.Exit:
        raise
    except Exception as exc:
        typer.secho(f"Discovery failed: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc


__all__ = ["discover"]
