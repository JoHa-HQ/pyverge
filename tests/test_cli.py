"""End-to-end CLI tests using the Typer runner."""

from __future__ import annotations

from pathlib import Path

import pytest
import semver
from typer.testing import CliRunner

from pyverge import Manager
from pyverge.cli.main import app
from pyverge.migration import JsonSchemaModelAdapter, PydanticModelAdapter
from pyverge.types import VersionValue
from tests.examples.json import USER_V1_0_0, USER_V2_0_0
from tests.examples.pydantic.semver import UserV1, UserV2, UserV3
from tests.utils import ManagerContext


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestManagersCommand:
    @pytest.mark.parametrize(
        ("model_adapter", "registry", "manager_name"),
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [UserV1, UserV2, UserV3], []],
                "e2e_pkg.pydantic",
                id="pydantic-manager",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [semver.Version, "test", [USER_V1_0_0, USER_V2_0_0], []],
                "e2e_pkg.json_schema",
                id="json-schema-manager",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_lists_managers_in_module(
        self,
        runner: CliRunner,
        snapshot,
        manager: type[Manager[VersionValue]],
        manager_name: str,
    ) -> None:
        """Test listing managers using a context manager."""
        with ManagerContext(manager_name, manager()):
            result = runner.invoke(app, ["managers", manager_name])
            assert result.exit_code == 0
            assert result.stdout == snapshot


class TestCheckCommand:
    @pytest.mark.parametrize(
        ("model_adapter", "registry", "manager_name"),
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [UserV1, UserV2, UserV3], []],
                "e2e_pkg.check.pydantic",
                id="pydantic-manager",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [semver.Version, "test", [USER_V1_0_0, USER_V2_0_0], []],
                "e2e_pkg.check.json_schema",
                id="json-schema-manager",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_check_valid_payload(
        self,
        runner: CliRunner,
        tmp_path: Path,
        manager: type[Manager[VersionValue]],
        manager_name: str,
    ) -> None:
        """Test checking a valid payload using a context manager."""
        data_file = tmp_path / "payload.json"
        data_file.write_text(
            '{"name": "Alice", "email": "alice@example.com", "role": "user"}'
        )

        with ManagerContext(manager_name, manager()):
            result = runner.invoke(
                app,
                [
                    "check",
                    "--data",
                    str(data_file),
                    "--schema",
                    "User",
                    "--version",
                    "1.0.0",
                    "--manager",
                    f"{manager_name}:manager",
                ],
            )

            assert result.exit_code == 0
            assert "Valid" in result.stdout

    @pytest.mark.parametrize(
        ("model_adapter", "registry", "manager_name"),
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [UserV1, UserV2, UserV3], []],
                "e2e_pkg.check.pydantic",
                id="pydantic-manager",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [semver.Version, "test", [USER_V1_0_0, USER_V2_0_0], []],
                "e2e_pkg.check.json_schema",
                id="json-schema-manager",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_check_invalid_payload_exits_1(
        self,
        runner: CliRunner,
        tmp_path: Path,
        manager: type[Manager[VersionValue]],
        manager_name: str,
    ) -> None:
        """Test checking an invalid payload using a context manager."""
        data_file = tmp_path / "payload.json"
        data_file.write_text('{"name": 123}')

        with ManagerContext(manager_name, manager()):
            result = runner.invoke(
                app,
                [
                    "check",
                    "--data",
                    str(data_file),
                    "--schema",
                    "User",
                    "--version",
                    "1.0.0",
                    "--manager",
                    f"{manager_name}:manager",
                ],
            )

            assert result.exit_code == 1


class TestInfoCommand:
    @pytest.mark.parametrize(
        ("model_adapter", "registry", "manager_name"),
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [UserV1, UserV2, UserV3], []],
                "e2e_pkg.container.pydantic",
                id="pydantic-manager",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [semver.Version, "test", [USER_V1_0_0, USER_V2_0_0], []],
                "e2e_pkg.container.json_schema",
                id="json-schema-manager",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_info_lists_registered_models(
        self,
        runner: CliRunner,
        snapshot,
        manager: type[Manager[VersionValue]],
        manager_name: str,
    ) -> None:
        """Test listing registered models using a context manager."""
        with ManagerContext(manager_name, manager()):
            result = runner.invoke(app, ["info", f"{manager_name}:manager"])

            assert result.exit_code == 0
            assert result.stdout == snapshot

    def test_info_unknown_manager_exits_1(self, runner: CliRunner) -> None:
        """Test info command with an unknown manager."""
        result = runner.invoke(app, ["info", "e2e_pkg.missing:manager"])

        assert result.exit_code == 1


class TestDiffCommand:
    @pytest.mark.parametrize(
        ("model_adapter", "registry", "manager_name"),
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [UserV1, UserV2, UserV3], []],
                "e2e_pkg.diff.pydantic",
                id="pydantic-manager",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [semver.Version, "test", [USER_V1_0_0, USER_V2_0_0], []],
                "e2e_pkg.diff.json_schema",
                id="json-schema-manager",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_diff_renders_json_patch(
        self,
        runner: CliRunner,
        snapshot,
        manager: type[Manager[VersionValue]],
        manager_name: str,
    ) -> None:
        """Test diff command renders JSON patch using a context manager."""
        with ManagerContext(manager_name, manager()):
            result = runner.invoke(
                app,
                [
                    "diff",
                    "--schema",
                    "User",
                    "--from",
                    "1.0.0",
                    "--to",
                    "2.0.0",
                    "--manager",
                    f"{manager_name}:manager",
                ],
            )

            assert result.exit_code == 0
            assert result.stdout == snapshot
