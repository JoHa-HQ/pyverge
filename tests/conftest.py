"""Shared test fixtures.

Imports model declarations from examples and exposes them as pytest fixtures.
Each fixture name reflects the use case it is designed to exercise.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path

import pytest
from click.testing import Result
from typer.testing import CliRunner

from pydantic_migrator import Coordinator
from pydantic_migrator.cli.main import app
from pydantic_migrator.migration import MigrationEngine, ModelManager
from pydantic_migrator.models import ManagerSettings
from tests.examples.default import DefaultManager

# from tests.examples.eager import UserContainer as EagerUserContainer
# from tests.examples.eager import eager_manager


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def application(runner: CliRunner) -> Callable[..., Result]:
    return partial(runner.invoke, app)


@pytest.fixture
def engine() -> MigrationEngine:
    """Engine backed by DefaultManager's class-level registry."""
    return MigrationEngine(DefaultManager.registry)


# @pytest.fixture
# def default_manager() -> DefaultManager:
#     return DefaultManager(ManagerSettings(version_property="version"))


# @pytest.fixture
# def eager_manager_instance() -> ModelManager[EagerUserContainer]:
#     return eager_manager


@pytest.fixture
def coordinator() -> Coordinator:  # pragma: no cover
    """Coordinator with multiple model families — skipped due to coordination.py issues."""
    return Coordinator()


@pytest.fixture
def project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Use the pre-defined default.py example as the project source."""
    cfg = tmp_path / "migrator.toml"
    cfg.write_text(
        '[pydantic-migrator]\nmanager = "tests.examples.default:DefaultManager"\n'
    )
    monkeypatch.syspath_prepend(str(tmp_path.parent.parent.parent))
    return tmp_path


@pytest.fixture
def sample_data(project_dir: Path) -> Path:
    """Create sample JSON data file with version field."""
    data = project_dir / "data.json"
    data.write_text(
        '{"version": "1.0.0", "name": "Alice", "email": "alice@example.com", "role": "user"}'
    )
    return data


@pytest.fixture
def config(project_dir: Path) -> list[str]:
    return ["-c", str(project_dir / "migrator.toml")]
