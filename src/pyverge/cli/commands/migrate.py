"""Migrate a payload file."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from .._helpers import load_json_file, write_json_file
from ..config import ConfigError, resolve_manager
from ._shared import ManagerOption, dump_json


def migrate(
    data: Annotated[Path, typer.Argument(help="Payload JSON file")],
    manager: ManagerOption,
    target: Annotated[
        str, typer.Option("--target", "-t", help="Target policy/version")
    ] = "latest",
    context: Annotated[
        str | None, typer.Option("--context", help="Context JSON object")
    ] = None,
    context_file: Annotated[
        Path | None, typer.Option("--context-file", help="Context JSON file")
    ] = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write migrated payload")
    ] = None,
    in_place: Annotated[
        bool, typer.Option("--in-place", help="Overwrite the input payload")
    ] = False,
    check: Annotated[
        bool, typer.Option("--check", help="Fail if migration does not converge")
    ] = False,
) -> None:
    """Migrate a payload and optionally write the result."""
    if output is not None and in_place:
        typer.secho(
            "--output and --in-place are mutually exclusive", fg=typer.colors.RED
        )
        raise typer.Exit(2)
    try:
        mgr = resolve_manager(manager)
        payload = load_json_file(data)
        runtime_context = None
        if context_file is not None:
            runtime_context = load_json_file(context_file)
        elif context is not None:
            runtime_context = json.loads(context)

        result = mgr.prepare(payload, target=target).run(context=runtime_context)  # ty: ignore[unresolved-attribute]

        if check:
            raise typer.Exit(0)
        if in_place:
            write_json_file(data, result)
        elif output is not None:
            write_json_file(output, result)
        else:
            dump_json(result)
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1) from exc
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1) from exc
    except typer.Exit:
        raise
    except Exception as exc:
        typer.secho(f"Migration failed: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc
