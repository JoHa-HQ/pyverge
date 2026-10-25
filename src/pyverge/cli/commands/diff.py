from __future__ import annotations

import json
from typing import Annotated

import typer

from pyverge.core.types import ManagerMigrationKey
from pyverge.discovery.reflection import JsonPatchRenderer

from ..config import ConfigError, resolve_manager
from ._shared import ManagerOption


def diff(
    schema: Annotated[str, typer.Option(..., "--schema", "-s", help="Schema name")],
    from_version: Annotated[
        str, typer.Option(..., "--from", "-f", help="Source version")
    ],
    to_version: Annotated[str, typer.Option(..., "--to", "-t", help="Target version")],
    manager: ManagerOption,
    format: Annotated[
        str, typer.Option(..., "--format", help="Output format (json)")
    ] = "json",
) -> None:
    try:
        mgr = resolve_manager(manager)
        diff_result = mgr.diff(ManagerMigrationKey(schema, from_version, to_version))

        if format == "json":
            typer.echo(
                json.dumps(
                    diff_result.render(JsonPatchRenderer()), indent=2, default=str
                )
            )
        else:
            typer.secho(f"Unknown format: {format}", fg=typer.colors.RED)
            raise typer.Exit(1)

    except ConfigError as e:
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(1) from e
    except typer.Exit:
        raise
    except Exception as e:
        typer.secho(f"Diff error: {e}", fg=typer.colors.RED)
        raise typer.Exit(1) from e
