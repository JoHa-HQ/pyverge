"""CLI entrypoint: assemble commands into the Typer app."""

from __future__ import annotations

import typer

from .commands import (
    check,
    compat,
    diff,
    doctor,
    export,
    info,
    init,
    managers,
    manifest,
    migrate,
    validate,
)

app = typer.Typer(help="Schema evolution and migrations for versioned models")

commands = (
    check,
    managers,
    manifest,
    info,
    diff,
    doctor,
    migrate,
    validate,
    compat,
    init,
    export,
)
for command in commands:
    app.command()(command)


if __name__ == "__main__":
    app()
