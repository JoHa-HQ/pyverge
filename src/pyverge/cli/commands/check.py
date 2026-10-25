from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from .._helpers import load_json_file
from ..config import ConfigError, resolve_manager
from ._shared import ManagerOption


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
