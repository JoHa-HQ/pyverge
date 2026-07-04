"""Tests for ModelManager API."""

from __future__ import annotations

import pytest
from pydantic import BaseModel
from syrupy.assertion import SnapshotAssertion

from pydantic_migrator.migration import ModelManager
from pydantic_migrator.migration.diff import ModelDiff, ModelDiffRenderer
from pydantic_migrator.migration.exceptions import MigrationError
from pydantic_migrator.migration.hooks import MetricsHook, MigrationHook
from pydantic_migrator.migration.versioning import ModelVersion
from pydantic_migrator.models import ManagerSettings
from pydantic_migrator.strategies import BatchMigrator


class TrackingHook(MigrationHook):
    """Records hook call order for assertion."""

    def __init__(self) -> None:
        self.events: list[str] = []

    def before_migrate(self, name, from_version, to_version, data):
        self.events.append(f"before:{name}:{from_version}->{to_version}")

    def after_migrate(
        self, name, from_version, to_version, original_data, migrated_data
    ):
        self.events.append(f"after:{name}:{from_version}->{to_version}")

    def on_error(self, name, from_version, to_version, data, error):
        self.events.append(f"error:{name}:{from_version}->{to_version}")


# ---------------------------------------------------------------------------
# Registration & introspection
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_list_models(self, default_manager: ModelManager) -> None:
        assert default_manager.list_models() == ["User"]

    def test_list_versions(self, default_manager: ModelManager) -> None:
        assert default_manager.list_versions() == [
            ModelVersion.parse("1.0.0"),
            ModelVersion.parse("2.0.0"),
            ModelVersion.parse("3.0.0"),
        ]

    def test_get_latest(self, default_manager: ModelManager) -> None:
        latest = default_manager.get_model()
        assert set(latest.model_fields.keys()) == {
            "name",
            "email",
            "age",
            "role",
            "status",
        }


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


class TestMigration:
    def test_single_migration(
        self, default_manager: ModelManager, snapshot: SnapshotAssertion
    ) -> None:
        migrated = default_manager.migrate(
            {
                "version": "1.0.0",
                "name": "Alice",
                "email": "alice@example.com",
                "role": "admin",
            },
            "1.0.0",
            "3.0.0",
        )
        assert migrated.model_dump(mode="json") == snapshot

    def test_batch_migration(self, default_manager: ModelManager) -> None:
        batch_in = [
            {"version": "1.0.0", "name": "Bob", "email": "bob@x.com", "role": "user"},
            {
                "version": "1.0.0",
                "name": "Carol",
                "email": "carol@x.com",
                "role": "guest",
            },
        ]
        results = BatchMigrator(default_manager).migrate(batch_in, "1.0.0", "3.0.0")
        assert len(results) == 2


class TestValidation:
    def test_valid_data(self, default_manager: ModelManager) -> None:
        v1_data = {
            "version": "1.0.0",
            "name": "Alice",
            "email": "alice@example.com",
            "role": "admin",
        }
        assert default_manager.validate_data(v1_data, "User", "1.0.0") is True

    def test_invalid_data(self, default_manager: ModelManager) -> None:
        assert (
            default_manager.validate_data(
                {"version": "1.0.0", "bad": True}, "User", "1.0.0"
            )
            is False
        )


class TestHooks:
    def test_tracking_hook(self, default_manager: ModelManager) -> None:
        hook = TrackingHook()
        default_manager.add_hook(hook, ModelVersion.parse("2.0.0"))
        default_manager.migrate(
            {
                "version": "1.0.0",
                "name": "Alice",
                "email": "alice@example.com",
                "role": "admin",
            },
            "1.0.0",
            "2.0.0",
        )
        assert "before:User:1.0.0->2.0.0" in hook.events
        assert "after:User:1.0.0->2.0.0" in hook.events
        default_manager.remove_hook(hook, ModelVersion.parse("2.0.0"))

    def test_metrics_hook(self, default_manager: ModelManager) -> None:
        metrics = MetricsHook()
        default_manager.add_hook(metrics, ModelVersion.parse("3.0.0"))
        default_manager.migrate(
            {
                "version": "1.0.0",
                "name": "Alice",
                "email": "alice@example.com",
                "role": "admin",
            },
            "1.0.0",
            "3.0.0",
        )
        v2_data = {
            "version": "2.0.0",
            "name": "Bob",
            "email": "bob@x.com",
            "age": 30,
            "role": "user",
        }
        default_manager.migrate(v2_data, "2.0.0", "3.0.0")
        assert metrics.total_count == 2
        assert metrics.error_count == 0
        assert metrics.success_rate == 1.0
        default_manager.clear_hooks()


class TestDiff:
    def test_diff_added_fields(self, default_manager: ModelManager) -> None:
        diff = default_manager.diff("1.0.0", "2.0.0")
        assert isinstance(diff, ModelDiff)
        assert "age" in diff.added_fields

    def test_diff_markdown(self, default_manager: ModelManager, snapshot) -> None:
        diff = default_manager.diff("1.0.0", "2.0.0")
        assert ModelDiffRenderer.to_markdown(diff) == snapshot


class TestMigrationPaths:
    def test_has_path(self, default_manager: ModelManager) -> None:
        assert default_manager.has_migration_path("1.0.0", "3.0.0")

    def test_no_reverse_path(self, default_manager: ModelManager) -> None:
        assert not default_manager.has_migration_path("3.0.0", "1.0.0")

    def test_no_path_raises(self, default_manager: ModelManager) -> None:
        with pytest.raises(MigrationError):
            default_manager.migrate(
                {"version": "1.0.0", "name": "X", "email": "x@x.com", "role": "user"},
                "3.0.0",
                "1.0.0",
            )


# ---------------------------------------------------------------------------
# Isolated instance-level registration (merged from test_isolation.py)
# ---------------------------------------------------------------------------


class TestIsolatedMigration:
    def test_v1_to_v2(self, snapshot: SnapshotAssertion) -> None:
        manager = ModelManager["TestContainer"](
            ManagerSettings(version_property="version")
        )

        @manager.model()
        class TestV1(BaseModel):
            name: str
            version: str = "1.0.0"

        @manager.model()
        class TestV2(BaseModel):
            name: str
            email: str
            version: str = "2.0.0"

        @manager.migration("1.0.0", "2.0.0")
        def migrate(data: dict) -> dict:
            data["email"] = f"{data['name']}@test.com"
            return data

        v1_data = {"version": "1.0.0", "name": "Alice"}
        v2_result = manager.migrate(v1_data, "1.0.0", "2.0.0")
        assert v2_result.model_dump() == snapshot

    def test_v2_to_v3(self, snapshot: SnapshotAssertion) -> None:
        manager = ModelManager["TestContainer"](
            ManagerSettings(version_property="version")
        )

        @manager.model()
        class TestV2(BaseModel):
            name: str
            email: str
            version: str = "2.0.0"

        @manager.model()
        class TestV3(BaseModel):
            name: str
            email: str
            age: int
            version: str = "3.0.0"

        @manager.migration("2.0.0", "3.0.0")
        def migrate(data: dict) -> dict:
            data["age"] = 25
            return data

        v2_data = {"version": "2.0.0", "name": "Bob", "email": "bob@test.com"}
        v3_result = manager.migrate(v2_data, "2.0.0", "3.0.0")
        assert v3_result.model_dump() == snapshot
