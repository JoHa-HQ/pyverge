"""Tests for MigrationEngine using default.py examples."""

from __future__ import annotations

import pytest

from pydantic_migrator.migration.engine import MigrationEngine
from pydantic_migrator.migration.exceptions import MigrationError
from pydantic_migrator.migration.hooks import MigrationHook
from pydantic_migrator.migration.versioning import ModelVersion


class _CountingHook(MigrationHook):
    def __init__(self) -> None:
        self.before_count = 0
        self.after_count = 0
        self.error_count = 0

    def before_migrate(self, name, from_version, to_version, data):
        self.before_count += 1

    def after_migrate(
        self, name, from_version, to_version, original_data, migrated_data
    ):
        self.after_count += 1

    def on_error(self, name, from_version, to_version, data, error):
        self.error_count += 1


class TestSingleStepMigration:
    def test_v1_to_v2(self, engine: MigrationEngine) -> None:
        result = engine.migrate(
            {"name": "Alice", "email": "a@b.com", "role": "user"},
            ModelVersion.parse("1.0.0"),
            ModelVersion.parse("2.0.0"),
        )
        assert result == {
            "name": "Alice",
            "email": "a@b.com",
            "role": "user",
            "age": None,
        }

    def test_same_version_noop(self, engine: MigrationEngine) -> None:
        result = engine.migrate(
            {"name": "Alice"}, ModelVersion.parse("1.0.0"), ModelVersion.parse("1.0.0")
        )
        assert result == {"name": "Alice"}

    def test_missing_migration_raises(self, engine: MigrationEngine) -> None:
        with pytest.raises(MigrationError):
            engine.migrate(
                {"name": "Alice"},
                ModelVersion.parse("1.0.0"),
                ModelVersion.parse("3.0.0"),
            )

    def test_missing_version_raises(self, engine: MigrationEngine) -> None:
        with pytest.raises(MigrationError):
            engine.migrate(
                {"name": "Alice"},
                ModelVersion.parse("1.0.0"),
                ModelVersion.parse("9.9.9"),
            )


class TestMultiStepMigration:
    def test_v1_to_v3_two_steps(self, engine: MigrationEngine) -> None:
        result = engine.migrate(
            {"name": "Alice", "email": "a@b.com", "role": "admin"},
            ModelVersion.parse("1.0.0"),
            ModelVersion.parse("3.0.0"),
        )
        assert result == {
            "name": "Alice",
            "email": "a@b.com",
            "role": "admin",
            "age": 0,
            "status": "active",
        }

    def test_v2_to_v3_single_step(self, engine: MigrationEngine) -> None:
        result = engine.migrate(
            {"name": "Bob", "email": "b@b.com", "role": "guest", "age": 25},
            ModelVersion.parse("2.0.0"),
            ModelVersion.parse("3.0.0"),
        )
        assert result == {
            "name": "Bob",
            "email": "b@b.com",
            "role": "guest",
            "age": 25,
            "status": "active",
        }


class TestHooks:
    def test_hooks_fire_on_single_step(self, engine: MigrationEngine) -> None:
        hook = _CountingHook()
        engine.registry.add_hook(
            hook, ModelVersion.parse("1.0.0"), ModelVersion.parse("2.0.0")
        )

        engine.migrate(
            {"name": "Alice", "email": "a@b.com", "role": "user"},
            ModelVersion.parse("1.0.0"),
            ModelVersion.parse("2.0.0"),
        )
        assert hook.before_count == 1
        assert hook.after_count == 1

    def test_hooks_fire_per_step_in_chain(self, engine: MigrationEngine) -> None:
        hook = _CountingHook()
        engine.registry.add_hook(
            hook, ModelVersion.parse("1.0.0"), ModelVersion.parse("2.0.0")
        )
        engine.registry.add_hook(
            hook, ModelVersion.parse("2.0.0"), ModelVersion.parse("3.0.0")
        )

        engine.migrate(
            {"name": "Alice", "email": "a@b.com", "role": "user"},
            ModelVersion.parse("1.0.0"),
            ModelVersion.parse("3.0.0"),
        )
        assert hook.before_count == 2
        assert hook.after_count == 2

    def test_error_hook(self, engine: MigrationEngine) -> None:
        # Register a failing migration
        def _failing(data: dict) -> dict:
            raise ValueError("boom")

        engine.registry.store_migration(
            ModelVersion.parse("2.0.0"), ModelVersion.parse("3.0.0"), _failing
        )
        hook = _CountingHook()
        engine.registry.add_hook(
            hook, ModelVersion.parse("2.0.0"), ModelVersion.parse("3.0.0")
        )

        with pytest.raises(MigrationError):
            engine.migrate(
                {"name": "Alice", "email": "a@b.com", "role": "user", "age": 25},
                ModelVersion.parse("2.0.0"),
                ModelVersion.parse("3.0.0"),
            )
        assert hook.error_count == 1


class TestAutoMigration:
    def test_auto_migrate_adds_field_default(self, engine: MigrationEngine) -> None:
        """UserV2 is backward_compatible — auto-migration should add defaults."""
        from_model = engine.registry.get_model(ModelVersion.parse("1.0.0"))
        to_model = engine.registry.get_model(ModelVersion.parse("2.0.0"))

        result = engine._auto_migrate_base_models(
            {"name": "Alice", "email": "a@b.com", "role": "user"},
            from_model,
            to_model,
        )
        assert result == {
            "name": "Alice",
            "email": "a@b.com",
            "role": "user",
            "age": None,
        }

    def test_auto_migrate_preserves_extra_fields(self, engine: MigrationEngine) -> None:
        from_model = engine.registry.get_model(ModelVersion.parse("1.0.0"))
        to_model = engine.registry.get_model(ModelVersion.parse("2.0.0"))

        result = engine._auto_migrate_base_models(
            {"name": "Alice", "email": "a@b.com", "role": "user", "legacy": True},
            from_model,
            to_model,
        )
        assert result == {
            "name": "Alice",
            "email": "a@b.com",
            "role": "user",
            "legacy": True,
            "age": None,
        }


class TestAliasMap:
    def test_field_name_from_UserV1(self, engine: MigrationEngine) -> None:
        alias_map = engine._build_alias_map(UserV1.model_fields)
        assert alias_map == {
            "name": "name",
            "email": "email",
            "role": "role",
            "version": "version",
        }
