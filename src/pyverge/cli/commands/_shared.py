from __future__ import annotations

import json
from typing import Annotated, Any

import typer
from rich.console import Console

console = Console()

ManagerOption = Annotated[
    str,
    typer.Option(
        ...,
        "--manager",
        "-m",
        help="Manager import path (module:object_path)",
    ),
]
SchemaOption = Annotated[
    str,
    typer.Option(..., "--schema", "-s", help="Schema name"),
]
VersionOption = Annotated[
    str,
    typer.Option(..., "--version", "-v", help="Schema version"),
]


def dump_json(value: Any) -> None:
    typer.echo(json.dumps(value, indent=2, default=str))
