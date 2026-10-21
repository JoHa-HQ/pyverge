"""End-to-end CLI tests using the Typer runner."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import semver
from typer.testing import CliRunner

from pyverge import Manager
from pyverge.cli.main import app
from pyverge.core.types import (
    VersionValue,
)
from pyverge.migration import JsonSchemaModelAdapter, PydanticModelAdapter
from tests.examples.json import USER_V1_0_0, USER_V2_0_0
from tests.examples.pydantic.semver import (
    UserV1,
    UserV2,
    UserV3,
    migrate_v1_to_v2,
)
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


@pytest.mark.parametrize(
    ("model_adapter", "registry", "manager_name"),
    [
        pytest.param(
            PydanticModelAdapter,
            [
                semver.Version,
                "test",
                [UserV1, UserV2],
                [((UserV1, UserV2), migrate_v1_to_v2)],
            ],
            "e2e_pkg.dx.pydantic",
            id="pydantic-manager",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
class TestCommands:
    def test_doctor_json(
        self,
        runner: CliRunner,
        manager: type[Manager[VersionValue]],
        manager_name: str,
    ) -> None:
        with ManagerContext(manager_name, manager()):
            result = runner.invoke(
                app, ["doctor", "-m", f"{manager_name}:manager", "--format", "json"]
            )

        assert result.exit_code == 0
        assert json.loads(result.stdout)["status"] == "ok"

    def test_doctor_resolves_runtime_factory(
        self,
        runner: CliRunner,
        manager: type[Manager[VersionValue]],
        manager_name: str,
    ) -> None:
        with ManagerContext(manager_name, manager()):
            # Factory builds the manager from a runtime source.
            setattr(sys.modules[manager_name], "create_manager", manager)
            result = runner.invoke(
                app,
                [
                    "doctor",
                    "-m",
                    f"{manager_name}:create_manager",
                    "--format",
                    "json",
                ],
            )

        assert result.exit_code == 0
        assert json.loads(result.stdout)["status"] == "ok"

    def test_validate_batch_reports_invalid(
        self,
        runner: CliRunner,
        tmp_path: Path,
        manager: type[Manager[VersionValue]],
        manager_name: str,
    ) -> None:
        valid = tmp_path / "valid.json"
        valid.write_text('{"name": "Alice", "email": "a@example.com", "role": "user"}')
        invalid = tmp_path / "invalid.json"
        invalid.write_text('{"name": 1}')

        with ManagerContext(manager_name, manager()):
            result = runner.invoke(
                app,
                [
                    "validate",
                    str(valid),
                    str(invalid),
                    "-m",
                    f"{manager_name}:manager",
                    "-s",
                    "User",
                    "-v",
                    "1.0.0",
                    "--format",
                    "json",
                ],
            )

        assert result.exit_code == 1
        results = json.loads(result.stdout)["results"]
        assert [item["valid"] for item in results] == [True, False]

    def test_migrate_writes_output(
        self,
        runner: CliRunner,
        tmp_path: Path,
        manager: type[Manager[VersionValue]],
        manager_name: str,
    ) -> None:
        source = tmp_path / "payload.json"
        source.write_text(
            '{"kind": "User", "version": "1.0.0", "name": "Alice", '
            '"email": "a@example.com", "role": "user"}'
        )
        output = tmp_path / "migrated.json"

        with ManagerContext(manager_name, manager()):
            result = runner.invoke(
                app,
                [
                    "migrate",
                    str(source),
                    "-m",
                    f"{manager_name}:manager",
                    "--output",
                    str(output),
                ],
            )

        assert result.exit_code == 0
        assert json.loads(output.read_text())["version"] == "2.0.0"

    def test_compat_json(
        self,
        runner: CliRunner,
        manager: type[Manager[VersionValue]],
        manager_name: str,
    ) -> None:
        with ManagerContext(manager_name, manager()):
            result = runner.invoke(
                app,
                ["compat", "-m", f"{manager_name}:manager", "--format", "json"],
            )

        assert result.exit_code == 0
        assert json.loads(result.stdout)["breaking"] is False

    def test_manifest_is_jgf_envelope(
        self,
        runner: CliRunner,
        manager: type[Manager[VersionValue]],
        manager_name: str,
    ) -> None:
        with ManagerContext(manager_name, manager()):
            result = runner.invoke(
                app, ["manifest", "-m", f"{manager_name}:manager"]
            )

        assert result.exit_code == 0
        envelope = json.loads(result.stdout)
        assert set(envelope) == {"graph"}
        graph = envelope["graph"]
        assert graph["directed"] is True
        assert graph["nodes"]["User@1.0.0"]["metadata"]["kind"] == "User"
        assert graph["edges"][0]["source"] == "User@1.0.0"
        assert graph["edges"][0]["target"] == "User@2.0.0"
        assert graph["edges"][0]["metadata"]["strategy"] == "callable"
        assert graph["metadata"]["manifest_version"] == "1.0"
        assert all(c in "0123456789abcdef" for c in graph["metadata"]["content_hash"])

    def test_export_manifest(
        self,
        runner: CliRunner,
        manager: type[Manager[VersionValue]],
        manager_name: str,
    ) -> None:
        with ManagerContext(manager_name, manager()):
            result = runner.invoke(app, ["export", "-m", f"{manager_name}:manager"])

        assert result.exit_code == 0
        assert "User" in json.loads(result.stdout)["kinds"]


def test_init_scaffolds_project(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(app, ["init", str(tmp_path), "--pyproject"])

    assert result.exit_code == 0
    assert (tmp_path / "models.py").exists()
    assert (tmp_path / "pyproject.toml").exists()
