"""Tests for EntryMigration strategies."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
import semver

from pydantic_migrator.migration import (
    DiscoverySettings,
    GraphEntry,
    PydanticModelAdapter,
    Registry,
)
from pydantic_migrator.migration.exceptions import MigrationError
from pydantic_migrator.migration.strategy import DefaultEntryMigration
from pydantic_migrator.migration.types import ModelData
from tests.examples.pydantic.semver_nested import PersonV1, PersonV2
from tests.utils import envelope_model


class TestDefaultEntryMigration:
    @pytest.fixture
    def adapter(self) -> PydanticModelAdapter:
        return PydanticModelAdapter()

    @pytest.fixture
    def registry(self) -> Registry[semver.Version]:
        return Registry[semver.Version]()

    @pytest.fixture
    def discovery_settings(self) -> DiscoverySettings:
        return DiscoverySettings()

    @pytest.fixture
    def source(
        self, adapter: PydanticModelAdapter, discovery_settings: DiscoverySettings
    ) -> Any:
        return envelope_model(adapter, discovery_settings, PersonV1)

    @pytest.fixture
    def target(
        self, adapter: PydanticModelAdapter, discovery_settings: DiscoverySettings
    ) -> Any:
        return envelope_model(adapter, discovery_settings, PersonV2)

    @pytest.fixture
    def entry(self, source: Any, target: Any) -> GraphEntry[Any, Any]:
        return GraphEntry(
            path=(),
            source=source,
            target=target,
            steps=((source, target),),
            hooks=((),),
        )

    @pytest.fixture
    def execute_step(self) -> MagicMock:
        return MagicMock(return_value={"version": "2.0.0"})

    def test_noop_when_source_equals_target(
        self,
        adapter: PydanticModelAdapter,
        source: Any,
        execute_step: MagicMock,
    ) -> None:
        entry = GraphEntry(path=(), source=source, target=source, steps=())
        strategy = DefaultEntryMigration()
        current: ModelData = {"version": "1.0.0"}

        result = strategy.migrate(
            entry,
            current,
            execute_step=execute_step,
            adapter=adapter,
            version_property="version",
            direction="any",
            on_direction_violation="raise",
            on_missing_path="raise",
        ).run()

        assert result is current
        execute_step.assert_not_called()

    def test_raises_on_direction_violation(
        self,
        adapter: PydanticModelAdapter,
        entry: GraphEntry[Any, Any],
        execute_step: MagicMock,
    ) -> None:
        strategy = DefaultEntryMigration()

        with pytest.raises(MigrationError):
            strategy.migrate(
                entry,
                {"version": "1.0.0"},
                execute_step=execute_step,
                adapter=adapter,
                version_property="version",
                direction="backward",
                on_direction_violation="raise",
                on_missing_path="raise",
            ).run()

        execute_step.assert_not_called()

    def test_skips_on_direction_violation(
        self,
        adapter: PydanticModelAdapter,
        entry: GraphEntry[Any, Any],
        execute_step: MagicMock,
    ) -> None:
        strategy = DefaultEntryMigration()
        current: ModelData = {"version": "1.0.0"}

        result = strategy.migrate(
            entry,
            current,
            execute_step=execute_step,
            adapter=adapter,
            version_property="version",
            direction="backward",
            on_direction_violation="skip",
            on_missing_path="raise",
        ).run()

        assert result is current
        execute_step.assert_not_called()

    def test_executes_steps(
        self,
        adapter: PydanticModelAdapter,
        entry: GraphEntry[Any, Any],
        source: Any,
        target: Any,
        execute_step: MagicMock,
    ) -> None:
        strategy = DefaultEntryMigration()
        current: ModelData = {"version": "1.0.0"}

        result = strategy.migrate(
            entry,
            current,
            execute_step=execute_step,
            adapter=adapter,
            version_property="version",
            direction="any",
            on_direction_violation="raise",
            on_missing_path="raise",
        ).run()

        execute_step.assert_called_once_with(source, target, current, (), "version")
        assert result == {"version": "2.0.0"}

    def test_calls_adapter_finalize(
        self,
        adapter: PydanticModelAdapter,
        entry: GraphEntry[Any, Any],
        execute_step: MagicMock,
    ) -> None:
        finalized_entry = GraphEntry(
            path=entry.path,
            source=entry.source,
            target=entry.target,
            steps=entry.steps,
            hooks=entry.hooks,
            target_model=PersonV2,
        )
        adapter.finalize = MagicMock(return_value={"version": "2.0.0", "name": "Alice"})
        strategy = DefaultEntryMigration()

        strategy.migrate(
            finalized_entry,
            {"version": "1.0.0"},
            execute_step=execute_step,
            adapter=adapter,
            version_property="version",
            direction="any",
            on_direction_violation="raise",
            on_missing_path="raise",
        ).run()

        adapter.finalize.assert_called_once_with(PersonV2, {"version": "2.0.0"})

    def test_skips_on_missing_migration(
        self,
        adapter: PydanticModelAdapter,
        entry: GraphEntry[Any, Any],
        execute_step: MagicMock,
    ) -> None:
        execute_step.side_effect = MigrationError(
            "Person",
            entry.source,
            entry.target,
            "no path",
        )
        strategy = DefaultEntryMigration()
        current: ModelData = {"version": "1.0.0"}

        result = strategy.migrate(
            entry,
            current,
            execute_step=execute_step,
            adapter=adapter,
            version_property="version",
            direction="any",
            on_direction_violation="raise",
            on_missing_path="skip",
        ).run()

        assert result is current

    def test_raises_on_missing_migration(
        self,
        adapter: PydanticModelAdapter,
        entry: GraphEntry[Any, Any],
        execute_step: MagicMock,
    ) -> None:
        execute_step.side_effect = MigrationError(
            "Person",
            entry.source,
            entry.target,
            "no path",
        )
        strategy = DefaultEntryMigration()

        with pytest.raises(MigrationError):
            strategy.migrate(
                entry,
                {"version": "1.0.0"},
                execute_step=execute_step,
                adapter=adapter,
                version_property="version",
                direction="any",
                on_direction_violation="raise",
                on_missing_path="raise",
            ).run()
