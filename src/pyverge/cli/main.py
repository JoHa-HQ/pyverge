"""Command-line interface for pyverge."""

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
    list_available_managers,
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
        help="Manager name or import path (module:object_path)",
    ),
]

ConfigOption = Annotated[
    Path | None,
    typer.Option(
        ...,
        "--config",
        "-c",
        help="Path to config file (pyproject.toml or pyverge.toml)",
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
    manager: ManagerOption = "default",
    config: ConfigOption = None,
) -> None:
    """Check a payload against a schema version."""
    try:
        mgr = resolve_manager(manager, config)
        data_dict = load_json_file(data)

        is_valid = mgr.validate_data(data_dict, schema, version)

        if is_valid:
            typer.secho(f"✓ Valid against {schema} v{version}", fg=typer.colors.GREEN)
            if manager != "default":
                typer.echo(f"Using manager: {manager}")
            raise typer.Exit(0)

        typer.secho("✗ Validation failed", fg=typer.colors.RED)

        try:
            mgr.get(schema, version).model.model_validate(data_dict)
        except ValidationError as e:
            typer.secho("\nValidation errors:", fg=typer.colors.RED)
            for error in e.errors():
                field = ".".join(str(loc) for loc in error["loc"])
                typer.echo(f"  • {field}: {error['msg']}")
        except Exception as e:
            typer.echo(f"\n{e}")

        raise typer.Exit(1)

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
    config: ConfigOption = None,
) -> None:
    """List all available managers from configuration."""
    try:
        available = list_available_managers(config)

        if not available:
            typer.echo("No managers configured\n")
            typer.echo("Configuration can be added to:")
            typer.echo('  1. pyproject.toml: [tool.pyverge] manager = "models"')
            typer.echo('  2. pyverge.toml: [pyverge] manager = "models"')
            typer.echo("  3. Auto-discovery: Define __manager__ in models.py")
            return

        table = Table(title="Available Managers")
        table.add_column("Name", style="cyan")
        table.add_column("Module", style="green")

        for name, module in sorted(available.items()):
            table.add_row(name, module)

        console.print(table)
        typer.echo("\nUse with: pyverge validate --manager <name> ...")

    except ConfigError as e:
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(1) from e


@app.command()
def info(
    manager: Annotated[str, typer.Argument(..., help="Manager name")] = "default",
    config: ConfigOption = None,
) -> None:
    """Show information about a specific manager."""
    try:
        mgr = resolve_manager(manager, config)

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
def diff(  # noqa: PLR0913
    schema: Annotated[str, typer.Option(..., "--schema", "-s", help="Schema name")],
    from_version: Annotated[
        str, typer.Option(..., "--from", "-f", help="Source version")
    ],
    to_version: Annotated[str, typer.Option(..., "--to", "-t", help="Target version")],
    format: Annotated[
        str, typer.Option(..., "--format", help="Output format (json)")
    ] = "json",
    manager: ManagerOption = "default",
    config: ConfigOption = None,
) -> None:
    """Show differences between schema versions."""
    try:
        mgr = resolve_manager(manager, config)
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
