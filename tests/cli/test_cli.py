"""End-to-end CLI tests using the Typer runner."""

from __future__ import annotations

import sys
import types
from typing import Literal

import pytest
import semver
from pydantic import BaseModel
from typer.testing import CliRunner

from pyverge.cli.main import app
from pyverge.migration import ModelManager, PydanticModelAdapter


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _register_manager(name: str, manager: ModelManager) -> None:
    module = types.ModuleType(name)
    module.manager = manager
    sys.modules[name] = module


def _manager_with_model() -> ModelManager[semver.Version]:
    mgr = ModelManager[semver.Version].scoped(PydanticModelAdapter())()

    class UserV1(BaseModel):
        kind: Literal["User"] = "User"
        version: Literal["1.0.0"] = "1.0.0"
        name: str

    mgr.store_model(UserV1)
    return mgr


class TestManagersCommand:
    def test_no_config_reports_hint(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["managers"])
        assert result.exit_code == 0
        assert "No managers configured" in result.stdout


class TestInfoCommand:
    def test_info_lists_registered_models(self, runner: CliRunner) -> None:
        _register_manager("e2e_pkg.container", _manager_with_model())

        result = runner.invoke(app, ["info", "e2e_pkg.container:manager"])

        assert result.exit_code == 0
        assert "UserV1" in result.stdout
        assert "v1.0.0" in result.stdout

    def test_info_unknown_manager_exits_1(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["info", "e2e_pkg.missing:manager"])

        assert result.exit_code == 1
