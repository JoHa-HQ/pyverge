from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from .._helpers import load_json_file
from ..config import ConfigError, resolve_manager
from ._shared import ManagerOption, SchemaOption, VersionOption, dump_json


def validate(
    manager: ManagerOption,
    schema: SchemaOption,
    version: VersionOption,
    files: Annotated[
        list[Path] | None, typer.Argument(help="Payload files or directories")
    ] = None,
    stdin: Annotated[
        bool, typer.Option("--stdin", help="Read a payload from stdin")
    ] = False,
    format: Annotated[
        str, typer.Option("--format", help="Output format (text/json)")
    ] = "text",
    fail_fast: Annotated[
        bool, typer.Option("--fail-fast", help="Stop on first failure")
    ] = False,
) -> None:
    try:
        mgr = resolve_manager(manager)
        paths: list[Path] = []
        for file in files or []:
            if file.is_dir():
                paths.extend(sorted(file.rglob("*.json")))
            else:
                paths.append(file)
        if not paths and not stdin:
            typer.secho("No input files (or use --stdin)", fg=typer.colors.RED)
            raise typer.Exit(2)

        results: list[dict[str, Any]] = []
        failed = 0
        for path in paths:
            try:
                mgr.validate(load_json_file(path), schema, version)
                results.append({"path": str(path), "valid": True})
            except Exception as exc:
                failed += 1
                results.append({"path": str(path), "valid": False, "error": str(exc)})
                if fail_fast:
                    break
        if stdin:
            try:
                mgr.validate(json.load(sys.stdin), schema, version)
                results.append({"path": "<stdin>", "valid": True})
            except Exception as exc:
                failed += 1
                results.append({"path": "<stdin>", "valid": False, "error": str(exc)})

        if format == "json":
            dump_json({"schema": schema, "version": version, "results": results})
        else:
            for result in results:
                mark = "OK" if result["valid"] else "FAIL"
                typer.echo(f"{mark} {result['path']}")
                if not result["valid"]:
                    typer.echo(f"  {result['error']}")
        raise typer.Exit(0 if failed == 0 else 1)
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1) from exc
