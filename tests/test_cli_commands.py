from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from pydantic_migrator.cli.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a minimal pydantic-migrator project."""
    models = tmp_path / "models.py"
    models.write_text('''"""Versioned models."""

from pydantic import BaseModel
from pydantic_migrator import ModelManager

manager = ModelManager()


@manager.model("User", "1.0.0")
class UserV1(BaseModel):
    name: str
    email: str


@manager.model("User", "2.0.0")
class UserV2(BaseModel):
    name: str
    email: str
    age: int | None = None


@manager.migration("User", "1.0.0", "2.0.0")
def add_age(data):
    return {**data, "age": None}


__manager__ = manager
''')
    cfg = tmp_path / "migrator.toml"
    cfg.write_text('[pydantic-migrator]\nmanager = "models"\n')
    monkeypatch.syspath_prepend(str(tmp_path))
    return tmp_path


@pytest.fixture
def sample_data(project_dir: Path) -> Path:
    """Create sample JSON data file."""
    data = project_dir / "data.json"
    data.write_text('{"name": "Alice", "email": "alice@example.com"}')
    return data


@pytest.fixture
def config(project_dir: Path) -> list[str]:
    return ["-c", str(project_dir / "migrator.toml")]


def test_info(config: list[str]) -> None:
    result = runner.invoke(app, ["info", *config], catch_exceptions=False)
    assert result.exit_code == 0


def test_validate_valid(config: list[str], sample_data: Path) -> None:
    result = runner.invoke(
        app,
        ["validate", "-d", str(sample_data), "-s", "User", "-v", "1.0.0", *config],
        catch_exceptions=False,
    )
    assert result.exit_code == 0


def test_validate_invalid(config: list[str], tmp_path: Path) -> None:
    bad_data = tmp_path / "bad.json"
    bad_data.write_text('{"wrong": true}')
    result = runner.invoke(
        app,
        ["validate", "-d", str(bad_data), "-s", "User", "-v", "1.0.0", *config],
        catch_exceptions=False,
    )
    assert result.exit_code == 1


def test_migrate(config: list[str], sample_data: Path) -> None:
    result = runner.invoke(
        app,
        [
            "migrate",
            "-d",
            str(sample_data),
            "-s",
            "User",
            "-f",
            "1.0.0",
            "-t",
            "2.0.0",
            *config,
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0


def test_diff_markdown(config: list[str]) -> None:
    result = runner.invoke(
        app,
        [
            "diff",
            "-s",
            "User",
            "-f",
            "1.0.0",
            "-t",
            "2.0.0",
            "--format",
            "markdown",
            *config,
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0


def test_diff_json(config: list[str]) -> None:
    result = runner.invoke(
        app,
        [
            "diff",
            "-s",
            "User",
            "-f",
            "1.0.0",
            "-t",
            "2.0.0",
            "--format",
            "json",
            *config,
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0


def test_export_json_schema(config: list[str], tmp_path: Path) -> None:
    out = tmp_path / "schemas"
    result = runner.invoke(
        app,
        ["export", "-o", str(out), *config],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert out.is_dir()
