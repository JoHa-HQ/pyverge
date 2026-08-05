"""Helper functions for the CLI."""

import json
from pathlib import Path
from typing import Any

import typer


def load_json_file(path: Path) -> Any:
    """Load JSON file."""
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError as e:
        raise FileNotFoundError(f"Data file not found: {path}") from e
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(f"Invalid JSON in {path}", e.doc, e.pos) from e


def write_json_file(path: Path, data: dict[str, Any]) -> None:
    """Write JSON file."""
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
    except PermissionError as e:
        raise PermissionError(f"Cannot write to {path}: Permission denied") from e
    except OSError as e:
        raise OSError(f"Failed to write {path}: {e}") from e


def create_example_models_file(path: Path) -> None:
    """Create example models.py file."""
    if path.exists():
        typer.secho(f"Skipping: {path} already exists", fg=typer.colors.YELLOW)
        return

    try:
        path.write_text('''"""Versioned models managed by pyverge."""

from typing import Literal

import semver
from pydantic import BaseModel

from pyverge.migration import (
    MigrationSettings,
    ModelManager,
    PydanticModelAdapter,
)

# Create a scoped manager class
UserManager = ModelManager[semver.Version].scoped(
    PydanticModelAdapter(),
    settings=MigrationSettings(),
)


# Version 1: Initial user model
@UserManager.model()
class UserV1(BaseModel):
    """User model v1.0.0"""
    kind: Literal["User"] = "User"
    version: Literal["1.0.0"] = "1.0.0"
    name: str
    email: str


# Version 2: Add age field
@UserManager.model()
class UserV2(BaseModel):
    """User model v2.0.0"""
    kind: Literal["User"] = "User"
    version: Literal["2.0.0"] = "2.0.0"
    name: str
    email: str
    age: int | None = None


# Define migration
@UserManager.migration("User", "1.0.0", "2.0.0")
def add_age_field(data: dict) -> dict:
    """Add optional age field."""
    return {**data, "age": None}


# Export manager instance for CLI discovery
__manager__ = UserManager()


# Alternative: Factory function pattern
# def create_manager():
#     """Factory function for creating manager with custom setup."""
#     return UserManager()
#
# __manager__ = create_manager
''')
        typer.secho(f"Created {path}", fg=typer.colors.GREEN)
    except OSError as e:
        typer.secho(f"Failed to create {path}: {e}", fg=typer.colors.RED)
        raise


def create_single_manager_config(project_dir: Path, use_pyproject: bool) -> None:
    """Create single manager configuration."""
    try:
        if use_pyproject:
            config_file = project_dir / "pyproject.toml"
            config_content = """[tool.pyverge]
manager = "models"
"""
            if config_file.exists():
                typer.echo(f"\nAdd this to {config_file}:")
                typer.echo(config_content)
            else:
                config_file.write_text(f"""[project]
name = "{project_dir.name}"
version = "0.1.0"

{config_content}""")
                typer.secho(f"Created {config_file}", fg=typer.colors.GREEN)
        else:
            config_file = project_dir / "pyverge.toml"
            if not config_file.exists():
                config_file.write_text("""[pyverge]
manager = "models"

# Optional: Use factory function
# manager = "models:create_manager"

# Optional: Pass initialization arguments
# init_args = []
# [pyverge.init_kwargs]
# debug = false
""")
                typer.secho(f"Created {config_file}", fg=typer.colors.GREEN)
    except OSError as e:
        typer.secho(f"Failed to create config: {e}", fg=typer.colors.RED)
        raise


def create_multi_manager_config(project_dir: Path, use_pyproject: bool) -> None:
    """Create multi-manager configuration."""
    try:
        if use_pyproject:
            config_content = """[tool.pyverge.managers]
default = "models"
api_v1 = "api.v1.models"
api_v2 = "api.v2.models"

# Optional: Configure specific manager with init args
# [tool.pyverge.managers.api_v1]
# manager = "api.v1.models:create_manager"
# init_args = ["production"]
"""
        else:
            config_content = """[pyverge.managers]
default = "models"
api_v1 = "api.v1.models"
api_v2 = "api.v2.models"

# Optional: Configure specific manager with init args
# [pyverge.managers.api_v1]
# manager = "api.v1.models:create_manager"
# init_args = ["production"]
"""

        config_file = project_dir / (
            "pyproject.toml" if use_pyproject else "pyverge.toml"
        )

        if config_file.exists() and use_pyproject:
            typer.echo(f"\nAdd this to {config_file}:")
            typer.echo(config_content)
        else:
            if use_pyproject:
                config_file.write_text(f"""[project]
name = "{project_dir.name}"
version = "0.1.0"

{config_content}""")
            else:
                config_file.write_text(config_content)
            typer.secho(f"Created {config_file}", fg=typer.colors.GREEN)
    except OSError as e:
        typer.secho(f"Failed to create config: {e}", fg=typer.colors.RED)
        raise


def print_next_steps(multiple: bool) -> None:
    """Print next steps after initialization."""
    if multiple:
        typer.echo("\nMultiple managers configured:")
        typer.echo("  • default (models)")
        typer.echo("  • api_v1 (api.v1.models)")
        typer.echo("  • api_v2 (api.v2.models)")
        typer.echo("\nCommands:")
        typer.echo("  pyverge managers              - List all managers")
        typer.echo("  pyverge info api_v1           - Show manager details")
        typer.echo("  pyverge validate -M api_v1 ...  - Use specific manager")
    else:
        typer.echo("\nNext steps:")
        typer.echo("  1. Edit models.py to add your models")
        typer.echo("  2. Run: pyverge info")
        typer.echo("  3. Run: pyverge validate -d data.json -s User -v 1.0.0")
