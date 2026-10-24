"""Tests for MigrationEntry strategies."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from pyverge import types
from pyverge.migration import (
    DefaultEntryPlanner,
    DefaultMigrationEntry,
    EntryMigrationTask,
    GraphEntry,
    PydanticModelAdapter,
)
from pyverge.versioning.errors import MigrationApplicationError
from tests.examples.pydantic.semver_nested import PersonV1, PersonV2
from tests.utils import envelope_model
from tests.utils.settings import MigrationSettings as DiscoverySettings


class TestDefaultMigrationEntry:
    @pytest.fixture
    def source(
        self,
        model_adapter: PydanticModelAdapter,
        discovery_settings: DiscoverySettings,
    ) -> Any:
        return envelope_model(model_adapter, discovery_settings, PersonV1)

    @pytest.fixture
    def target(
        self,
        model_adapter: PydanticModelAdapter,
        discovery_settings: DiscoverySettings,
    ) -> Any:
        return envelope_model(model_adapter, discovery_settings, PersonV2)

    @pytest.fixture
    def entry(self, source: Any, target: Any) -> GraphEntry[Any]:
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
        model_adapter: PydanticModelAdapter,
        source: Any,
        execute_step: MagicMock,
    ) -> None:
        entry = GraphEntry(path=(), source=source, target=source, steps=())
        strategy = DefaultMigrationEntry()
        current: types.ModelData = {"version": "1.0.0"}

        result = strategy.migrate(
            entry,
            current,
            execute_step=execute_step,
            adapter=model_adapter,
            version_property="version",
            direction="any",
            on_direction_violation="raise",
            on_missing_path="raise",
        ).run()

        assert result is current
        execute_step.assert_not_called()

    def test_raises_on_direction_violation(
        self,
        model_adapter: PydanticModelAdapter,
        entry: GraphEntry[Any],
        execute_step: MagicMock,
    ) -> None:
        strategy = DefaultMigrationEntry()

        with pytest.raises(MigrationApplicationError):
            strategy.migrate(
                entry,
                {"version": "1.0.0"},
                execute_step=execute_step,
                adapter=model_adapter,
                version_property="version",
                direction="backward",
                on_direction_violation="raise",
                on_missing_path="raise",
            ).run()

        execute_step.assert_not_called()

    def test_skips_on_direction_violation(
        self,
        model_adapter: PydanticModelAdapter,
        entry: GraphEntry[Any],
        execute_step: MagicMock,
    ) -> None:
        strategy = DefaultMigrationEntry()
        current: types.ModelData = {"version": "1.0.0"}

        result = strategy.migrate(
            entry,
            current,
            execute_step=execute_step,
            adapter=model_adapter,
            version_property="version",
            direction="backward",
            on_direction_violation="skip",
            on_missing_path="raise",
        ).run()

        assert result is current
        execute_step.assert_not_called()

    def test_executes_steps(
        self,
        model_adapter: PydanticModelAdapter,
        entry: GraphEntry[Any],
        source: Any,
        target: Any,
        execute_step: MagicMock,
    ) -> None:
        strategy = DefaultMigrationEntry()
        current: types.ModelData = {"version": "1.0.0"}

        result = strategy.migrate(
            entry,
            current,
            execute_step=execute_step,
            adapter=model_adapter,
            version_property="version",
            direction="any",
            on_direction_violation="raise",
            on_missing_path="raise",
        ).run()

        execute_step.assert_called_once_with(
            source, target, current, (), "version", None
        )
        assert result == {"version": "2.0.0"}

    def test_planner_returns_task_without_executing(
        self,
        model_adapter: PydanticModelAdapter,
        entry: GraphEntry[Any],
        execute_step: MagicMock,
    ) -> None:
        planner = DefaultEntryPlanner()

        task = planner.migrate(
            entry,
            {"version": "1.0.0"},
            execute_step=execute_step,
            adapter=model_adapter,
            version_property="version",
            direction="any",
            on_direction_violation="raise",
            on_missing_path="raise",
        )

        assert isinstance(task, EntryMigrationTask)
        execute_step.assert_not_called()

        task.run()
        execute_step.assert_called_once()

    def test_async_planner_returns_task_without_executing(
        self,
        model_adapter: PydanticModelAdapter,
        entry: GraphEntry[Any],
    ) -> None:
        aexecute_step = AsyncMock(return_value={"version": "2.0.0"})
        planner = DefaultEntryPlanner()

        task = planner.amigrate(
            entry,
            {"version": "1.0.0"},
            aexecute_step=aexecute_step,
            adapter=model_adapter,
            version_property="version",
            direction="any",
            on_direction_violation="raise",
            on_missing_path="raise",
        )

        assert isinstance(task, EntryMigrationTask)
        aexecute_step.assert_not_called()

        asyncio.run(task.arun())
        aexecute_step.assert_called_once()

    def test_calls_adapter_finalize(
        self,
        model_adapter: PydanticModelAdapter,
        entry: GraphEntry[Any],
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
        model_adapter.finalize = MagicMock(
            return_value={"version": "2.0.0", "name": "Alice"}
        )
        strategy = DefaultMigrationEntry()

        strategy.migrate(
            finalized_entry,
            {"version": "1.0.0"},
            execute_step=execute_step,
            adapter=model_adapter,
            version_property="version",
            direction="any",
            on_direction_violation="raise",
            on_missing_path="raise",
        ).run()

        model_adapter.finalize.assert_called_once_with(PersonV2, {"version": "2.0.0"})

    def test_skips_on_missing_migration(
        self,
        model_adapter: PydanticModelAdapter,
        entry: GraphEntry[Any],
        execute_step: MagicMock,
    ) -> None:
        execute_step.side_effect = MigrationApplicationError(
            "Person",
            entry.source,
            entry.target,
            "no path",
        )
        strategy = DefaultMigrationEntry()
        current: types.ModelData = {"version": "1.0.0"}

        result = strategy.migrate(
            entry,
            current,
            execute_step=execute_step,
            adapter=model_adapter,
            version_property="version",
            direction="any",
            on_direction_violation="raise",
            on_missing_path="skip",
        ).run()

        assert result is current

    def test_raises_on_missing_migration(
        self,
        model_adapter: PydanticModelAdapter,
        entry: GraphEntry[Any],
        execute_step: MagicMock,
    ) -> None:
        execute_step.side_effect = MigrationApplicationError(
            "Person",
            entry.source,
            entry.target,
            "no path",
        )
        strategy = DefaultMigrationEntry()

        with pytest.raises(MigrationApplicationError):
            strategy.migrate(
                entry,
                {"version": "1.0.0"},
                execute_step=execute_step,
                adapter=model_adapter,
                version_property="version",
                direction="any",
                on_direction_violation="raise",
                on_missing_path="raise",
            ).run()
