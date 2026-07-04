"""Tests for Registry: model and migration registration."""

import pytest

from pydantic_migrator.migration.registry import Registry
from pydantic_migrator.migration.versioning import ModelVersion
from tests.examples.default import UserContainer, UserV1, UserV2, UserV3


def _v(s: str) -> ModelVersion:
    return ModelVersion.parse(s)


class TestModelRegistration:
    def test_store_and_get(self) -> None:
        registry = Registry(UserContainer)

        registry.store_model(UserV1, _v("1.0.0"))
        assert registry.get_model(_v("1.0.0")) is UserV1

    def test_versions_sorted(self) -> None:
        registry = Registry(UserContainer)

        registry.store_model(UserV3, _v("3.0.0"))
        registry.store_model(UserV1, _v("1.0.0"))
        registry.store_model(UserV2, _v("2.0.0"))

        assert registry.versions == [_v("1.0.0"), _v("2.0.0"), _v("3.0.0")]

    def test_latest(self) -> None:
        registry = Registry(UserContainer)

        registry.store_model(UserV1, _v("1.0.0"))
        registry.store_model(UserV2, _v("2.0.0"))

        assert registry.latest == _v("2.0.0")

    def test_get_nonexistent_raises(self) -> None:
        registry = Registry(UserContainer)
        registry.store_model(UserV1, _v("1.0.0"))

        with pytest.raises(ValueError, match="not found"):
            registry.get_model(_v("2.0.0"))

    def test_latest_empty_raises(self) -> None:
        registry = Registry(UserContainer)
        with pytest.raises(ValueError):
            _ = registry.latest

    def test_store_duplicate_overwrites(self) -> None:
        registry = Registry(UserContainer)
        registry.store_model(UserV1, _v("1.0.0"))
        registry.store_model(UserV2, _v("1.0.0"))

        assert registry.get_model(_v("1.0.0")) is UserV2
        assert len(registry.versions) == 1


class TestBackwardCompatible:
    def test_backward_compatible_flag(self) -> None:
        registry = Registry(UserContainer)
        registry.store_model(UserV1, _v("1.0.0"), backward_compatible=True)

        assert registry.is_backward_compatible(_v("1.0.0")) is True

    def test_not_backward_compatible_by_default(self) -> None:
        registry = Registry(UserContainer)
        registry.store_model(UserV1, _v("1.0.0"))

        assert registry.is_backward_compatible(_v("1.0.0")) is False


class TestRemoveModel:
    def test_remove_existing(self) -> None:
        registry = Registry(UserV1)
        registry.store_model(UserV1, _v("1.0.0"))
        registry.remove_model(_v("1.0.0"))

        assert _v("1.0.0") not in registry.versions

    def test_remove_nonexistent_raises(self) -> None:
        registry = Registry(UserV1)
        with pytest.raises(ValueError, match="not found"):
            registry.remove_model(_v("1.0.0"))

    def test_remove_cleans_migrations(self) -> None:
        registry = Registry(UserV1)
        registry.store_model(UserV1, _v("1.0.0"))
        registry.store_model(UserV2, _v("2.0.0"))

        def _noop(data: dict) -> dict:
            return data

        registry.store_migration(_v("1.0.0"), _v("2.0.0"), _noop)

        # Remove source version
        registry.remove_model(_v("1.0.0"))

        with pytest.raises(ValueError):
            registry.get_migration(_v("1.0.0"), _v("2.0.0"))

    def test_remove_intermediate(self) -> None:
        registry = Registry(UserV1)
        registry.store_model(UserV1, _v("1.0.0"))
        registry.store_model(UserV2, _v("2.0.0"))
        registry.store_model(UserV3, _v("3.0.0"))

        def _noop(data: dict) -> dict:
            return data

        registry.store_migration(_v("1.0.0"), _v("2.0.0"), _noop)
        registry.store_migration(_v("2.0.0"), _v("3.0.0"), _noop)

        # Remove intermediate version
        registry.remove_model(_v("2.0.0"))

        # Both migrations should be cleaned up
        with pytest.raises(ValueError):
            registry.get_migration(_v("1.0.0"), _v("2.0.0"))
        with pytest.raises(ValueError):
            registry.get_migration(_v("2.0.0"), _v("3.0.0"))

    def test_remove_cleans_backward_compatible(self) -> None:
        registry = Registry(UserV1)
        registry.store_model(UserV1, _v("1.0.0"), backward_compatible=True)

        registry.remove_model(_v("1.0.0"))
        assert registry.is_backward_compatible(_v("1.0.0")) is False


# ---------------------------------------------------------------------------
# Migration registration
# ---------------------------------------------------------------------------


class TestMigrationRegistration:
    def test_store_and_get(self) -> None:
        registry = Registry(UserV1)
        registry.store_model(UserV1, _v("1.0.0"))
        registry.store_model(UserV2, _v("2.0.0"))

        def _migrate(data: dict) -> dict:
            return data

        registry.store_migration(_v("1.0.0"), _v("2.0.0"), _migrate)
        assert registry.get_migration(_v("1.0.0"), _v("2.0.0")) is _migrate

    def test_get_nonexistent_raises(self) -> None:
        registry = Registry(UserV1)
        registry.store_model(UserV1, _v("1.0.0"))
        registry.store_model(UserV2, _v("2.0.0"))

        with pytest.raises(ValueError):
            registry.get_migration(_v("1.0.0"), _v("3.0.0"))
