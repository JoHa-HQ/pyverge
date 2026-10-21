"""Scaffold a project."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from .._helpers import (
    create_example_models_file,
    create_multi_manager_config,
    create_single_manager_config,
    print_next_steps,
)


def init(
    path: Annotated[Path, typer.Argument(help="Project directory")] = Path("."),
    use_pyproject: Annotated[
        bool, typer.Option("--pyproject", help="Write pyproject.toml config")
    ] = False,
    multiple: Annotated[
        bool, typer.Option("--multiple", help="Scaffold multi-manager config")
    ] = False,
) -> None:
    """Scaffold models and manager configuration."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        create_example_models_file(path / "models.py")
        if multiple:
            create_multi_manager_config(path, use_pyproject)
        else:
            create_single_manager_config(path, use_pyproject)
        print_next_steps(multiple)
    except OSError as exc:
        typer.secho(f"Initialization failed: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc
