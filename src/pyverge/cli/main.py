import json
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from ._helpers import (
    load_json_file,
)
from .config import (
    ConfigError,
    list_managers_from_module,
    resolve_manager,
)

app = typer.Typer(help="Schema evolution and migrations for versioned models")
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


@app.command()
def check(
    data: Annotated[
        Path, typer.Option(..., "--data", "-d", help="Path to data file (JSON)")
    ],
    schema: Annotated[str, typer.Option(..., "--schema", "-s", help="Schema name")],
    version: Annotated[
        str, typer.Option(..., "--version", "-v", help="Schema version")
    ],
    manager: ManagerOption,
) -> None:
    """Check a payload against a schema version."""
    try:
        mgr = resolve_manager(manager)
        data_dict = load_json_file(data)

        mgr.validate(data_dict, schema, version)

        typer.secho(f"✓ Valid against {schema} v{version}", fg=typer.colors.GREEN)
        raise typer.Exit(0)

    except ValidationError as e:
        typer.secho("✗ Validation failed", fg=typer.colors.RED)
        typer.secho("\nValidation errors:", fg=typer.colors.RED)
        for error in e.errors():
            field = ".".join(str(loc) for loc in error["loc"])
            typer.echo(f"  • {field}: {error['msg']}")
        raise typer.Exit(1) from e
    except ConfigError as e:
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(1) from e
    except FileNotFoundError as e:
        typer.secho(f"File not found: {e}", fg=typer.colors.RED)
        raise typer.Exit(1) from e
    except json.JSONDecodeError as e:
        typer.secho(f"Invalid JSON in {data}: {e}", fg=typer.colors.RED)
        raise typer.Exit(1) from e
    except typer.Exit:
        raise
    except Exception as e:
        typer.secho(f"Validation error: {e}", fg=typer.colors.RED)
        raise typer.Exit(1) from e


@app.command()
def managers(
    module: Annotated[
        str, typer.Argument(..., help="Module path to inspect for managers")
    ],
) -> None:
    """List ModelManagers defined in a module."""
    try:
        names = list_managers_from_module(module)

        table = Table(title=f"Managers in {module}")
        table.add_column("Name", style="cyan")

        for name in sorted(names):
            table.add_row(name)

        console.print(table)

    except ImportError as e:
        typer.secho(f"Cannot import module '{module}': {e}", fg=typer.colors.RED)
        raise typer.Exit(1) from e


@app.command()
def info(
    manager: Annotated[
        str, typer.Argument(..., help="Manager import path (module:object_path)")
    ],
) -> None:
    """Show information about a specific manager."""
    try:
        mgr = resolve_manager(manager)

        typer.secho(f"Manager: {manager}", bold=True)
        typer.echo("")

        versions = mgr.list_versions()
        models = sorted({v.model.__name__ for v in versions})

        if not models:
            typer.secho("No models registered", fg=typer.colors.YELLOW)
            return

        typer.secho("Registered Models:", bold=True)
        typer.echo("")

        for model_name in models:
            typer.secho(f"  {model_name}", bold=True)
            for v in versions:
                if v.model.__name__ == model_name:
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


@app.command()
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
    """Show differences between schema versions."""
    try:
        mgr = resolve_manager(manager)
        diff_result = mgr.diff(schema, from_version, to_version)

        if format == "json":
            typer.echo(json.dumps(diff_result.render(), indent=2, default=str))
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


if __name__ == "__main__":
    app()
