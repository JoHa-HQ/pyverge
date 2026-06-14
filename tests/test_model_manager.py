from __future__ import annotations

import tempfile
from pathlib import Path
from typing import cast

import pytest

from pydantic_migrator import (
    MetricsHook,
    MigrationHook,
    MigrationTestCase,
    ModelDiff,
    ModelManager,
    ModelVersion,
)
from pydantic_migrator.exceptions import MigrationError
from tests.conftest import Role, UserV2, UserV3


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
    def test_list_models(self, manager: ModelManager) -> None:
        assert set(manager.list_models()) == {"User", "Address"}

    def test_list_versions(self, manager: ModelManager) -> None:
        assert manager.list_versions("User") == [
            ModelVersion(1, 0, 0),
            ModelVersion(2, 0, 0),
            ModelVersion(3, 0, 0),
        ]

    def test_get_latest(self, manager: ModelManager) -> None:
        assert manager.get_latest("User").model_fields.keys() == {
            "name",
            "email",
            "age",
            "role",
            "status",
            "address",
        }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_valid_data(self, manager: ModelManager) -> None:
        v1_data = {"name": "Alice", "email": "alice@example.com", "role": "admin"}
        assert manager.validate_data(v1_data, "User", "1.0.0") is True

    def test_invalid_data(self, manager: ModelManager) -> None:
        assert manager.validate_data({"bad": True}, "User", "1.0.0") is False

    def test_single_migration(self, manager: ModelManager) -> None:
        migrated = cast(
            UserV3,
            manager.migrate(
                {"name": "Alice", "email": "alice@example.com", "role": "admin"},
                "User",
                "1.0.0",
                "3.0.0",
            ),
        )
        assert migrated.name == "Alice"
        assert migrated.role == Role.ADMIN
        assert migrated.age == 0
        assert migrated.status == "active"
        assert migrated.address.zip_code is None

    def test_migrate_as(self, manager: ModelManager) -> None:
        v2_data = manager.migrate_as(
            {"name": "Alice", "email": "alice@example.com", "role": "admin"},
            "User",
            "1.0.0",
            "2.0.0",
            UserV2,
        )
        assert v2_data.age is None
        assert v2_data.address.city == ""

    def test_batch_migration(self, manager: ModelManager) -> None:
        batch_in = [
            {"name": "Bob", "email": "bob@x.com", "role": "user"},
            {"name": "Carol", "email": "carol@x.com", "role": "guest"},
        ]
        results = cast(
            list[UserV3], manager.migrate_batch(batch_in, "User", "1.0.0", "3.0.0")
        )
        assert len(results) == 2  # noqa: PLR2004
        assert all(r.status == "active" for r in results)

    def test_streaming_batch_migration(self, manager: ModelManager) -> None:
        batch_in = [
            {"name": "Bob", "email": "bob@x.com", "role": "user"},
            {"name": "Carol", "email": "carol@x.com", "role": "guest"},
        ]
        stream_results = list(
            manager.migrate_batch_streaming(batch_in, "User", "1.0.0", "3.0.0")
        )
        assert len(stream_results) == 2  # noqa: PLR2004


def test_tracking_hook(manager: ModelManager) -> None:
    hook = TrackingHook()
    manager.add_hook(hook)
    manager.migrate(
        {"name": "Alice", "email": "alice@example.com", "role": "admin"},
        "User",
        "1.0.0",
        "2.0.0",
    )
    assert "before:User:1.0.0->2.0.0" in hook.events
    assert "after:User:1.0.0->2.0.0" in hook.events
    manager.remove_hook(hook)


def test_metrics_hook(manager: ModelManager) -> None:
    metrics = MetricsHook()
    manager.add_hook(metrics)
    manager.migrate(
        {"name": "Alice", "email": "alice@example.com", "role": "admin"},
        "User",
        "1.0.0",
        "3.0.0",
    )
    # Second call needs valid v2 data (has address fields)
    v2_data = {
        "name": "Bob",
        "email": "bob@x.com",
        "age": None,
        "role": "user",
        "address": {"street": "Main St", "city": "London"},
    }
    manager.migrate(v2_data, "User", "2.0.0", "3.0.0")
    assert metrics.total_count == 2  # noqa: PLR2004
    assert metrics.error_count == 0
    assert metrics.success_rate == 1.0
    manager.clear_hooks()


def test_migration_test_cases(manager: ModelManager) -> None:
    test_cases = [
        MigrationTestCase(
            source={"name": "Alice", "email": "alice@example.com", "role": "admin"},
            description="v1->v3 migration completes without error",
        ),
    ]
    test_results = manager.test_migration("User", "1.0.0", "3.0.0", test_cases)  # type: ignore[invalid-argument-type]  # ty:ignore[invalid-argument-type]
    assert test_results.all_passed


def test_diff_added_fields(manager: ModelManager) -> None:
    diff = manager.diff("User", "1.0.0", "2.0.0")
    assert isinstance(diff, ModelDiff)
    assert "address" in diff.added_fields
    assert "age" in diff.added_fields


def test_diff_markdown(manager: ModelManager, snapshot) -> None:
    diff = manager.diff("User", "1.0.0", "2.0.0")
    assert diff.to_markdown() == snapshot


def test_dump_schemas(manager: ModelManager, snapshot) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        manager.dump_schemas(tmp_path)
        files = {f.name: f.read_text() for f in tmp_path.glob("*.json")}
        assert files == snapshot


def test_has_path(manager: ModelManager) -> None:
    assert manager.has_migration_path("User", "1.0.0", "3.0.0")


def test_no_reverse_path(manager: ModelManager) -> None:
    assert not manager.has_migration_path("User", "3.0.0", "1.0.0")


def test_no_path_raises(manager: ModelManager) -> None:
    with pytest.raises(MigrationError):
        manager.migrate(
            {"name": "X", "email": "x@x.com", "role": "user"},
            "User",
            "3.0.0",
            "1.0.0",
        )
