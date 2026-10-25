from __future__ import annotations

from typing import Annotated

import typer
from rich import box
from rich.table import Table

from ..config import list_managers_from_module
from ._shared import console


def managers(
    module: Annotated[
        str, typer.Argument(..., help="Module path to inspect for managers")
    ],
) -> None:
    try:
        names = list_managers_from_module(module)

        table = Table(title=f"Managers in {module}", box=box.SQUARE)
        table.add_column("Name", style="cyan")

        for name in sorted(names):
            table.add_row(name)

        console.print(table)

    except ImportError as e:
        typer.secho(f"Cannot import module '{module}': {e}", fg=typer.colors.RED)
        raise typer.Exit(1) from e
