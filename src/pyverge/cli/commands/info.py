from __future__ import annotations

from typing import Annotated

import typer

from ..config import ConfigError, resolve_manager


def _display_model(model_id: str) -> str:
    return model_id.split("@", 1)[0].rsplit(".", 1)[-1]


def info(
    manager: Annotated[
        str, typer.Argument(..., help="Manager import path (module:object_path)")
    ],
) -> None:
    try:
        mgr = resolve_manager(manager)

        typer.secho(f"Manager: {manager}", bold=True)
        typer.echo("")

        versions = mgr.list_versions()
        models = sorted({_display_model(v.model_id) for v in versions})

        if not models:
            typer.secho("No models registered", fg=typer.colors.YELLOW)
            return

        typer.secho("Registered Models:", bold=True)
        typer.echo("")

        for model_name in models:
            typer.secho(f"  {model_name}", bold=True)
            for v in versions:
                if _display_model(v.model_id) == model_name:
                    typer.echo(f"    • v{v.version[1]}")

        typer.echo(f"\nTotal: {len(models)} models")

    except ConfigError as e:
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(1) from e
    except typer.Exit:
        raise
    except Exception as e:
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(1) from e
