"""Tests for migration strategies: batch, streaming, parallel.

Each strategy wraps a Manager and handles iteration/delegation.
The Manager provides only ``migrate(data, from_v, to_v)``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from syrupy import SnapshotAssertion

from pydantic_migrator.migration import ModelManager
from pydantic_migrator.models import ManagerSettings
from pydantic_migrator.strategies import (
    BatchMigrator,
    ParallelMigrator,
    StreamingMigrator,
)


class TestSingleMigration:
    """Manager.migrate — the only migration method on the Manager."""

    def test_migrate_single_item(self, snapshot: SnapshotAssertion) -> None:
        manager = ModelManager[
            "TestContainer", ManagerSettings(version_property="version")
        ]

        @manager.model()
        class UserV1(BaseModel):
            name: str
            version: str = Field(default="1.0.0", frozen=True)

        @manager.model()
        class UserV2(BaseModel):
            name: str
            email: str
            version: str = Field(default="2.0.0", frozen=True)

        @manager.migration("1.0.0", "2.0.0")
        def add_email(data: dict) -> dict:
            data["email"] = f"{data['name']}@test.com"
            return data

        user = manager.migrate({"name": "Alice", "version": "1.0.0"}, "1.0.0", "2.0.0")
        assert user.model_dump() == snapshot()


class TestBatchMigration:
    """Batch: wraps a manager, migrates a list."""

    def test_batch_migrate_all(self, default_manager: ModelManager) -> None:
        batch = [
            {"name": "Alice", "version": "1.0.0"},
            {"name": "Bob", "version": "1.0.0"},
        ]

        results = BatchMigrator(default_manager).migrate(batch, "1.0.0", "2.0.0")
        assert len(results) == 2
        assert results[0].email == "Alice@test.com"
        assert results[1].email == "Bob@test.com"

    def test_batch_empty_input(self, default_manager: ModelManager) -> None:
        results = BatchMigrator(default_manager).migrate([], "1.0.0", "2.0.0")
        assert results == []

    def test_batch_error_isolation(self, default_manager: ModelManager) -> None:
        batch = [
            {"name": "Good", "version": "1.0.0"},
            {"bad": True, "version": "1.0.0"},  # missing required field
            {"name": "AlsoGood", "version": "1.0.0"},
        ]

        migrator = BatchMigrator(default_manager, stop_on_error=False)
        results = migrator.migrate(batch, "1.0.0", "2.0.0")

        # Should get 2 successful results (skipped bad item)
        assert len(results) == 2
        assert results[0].name == "Good"
        assert results[1].name == "AlsoGood"


class TestStreamingMigration:
    """Streaming: wraps a manager, yields items lazily."""

    def test_streaming_chunks(self, default_manager: ModelManager) -> None:

        data = [{"name": f"User{i}", "version": "1.0.0"} for i in range(5)]

        results = list(
            StreamingMigrator(default_manager, chunk_size=2).migrate(
                data, "1.0.0", "2.0.0"
            )
        )
        assert len(results) == 5
        assert all(r.email.endswith("@test.com") for r in results)

    def test_streaming_empty_input(self, default_manager: ModelManager) -> None:

        results = list(StreamingMigrator(default_manager).migrate([], "1.0.0", "2.0.0"))
        assert results == []

    def test_streaming_smaller_than_chunk(self, default_manager: ModelManager) -> None:
        data = [{"name": "Single", "version": "1.0.0"}]

        results = list(
            StreamingMigrator(default_manager, chunk_size=10).migrate(
                data, "1.0.0", "2.0.0"
            )
        )
        assert len(results) == 1
        assert results[0].name == "Single"


class TestParallelMigration:
    """Parallel: wraps a manager, migrates concurrently."""

    def test_parallel_migrate(self) -> None:
        manager = _setup_two_version_manager()

        data = [{"name": f"User{i}", "version": "1.0.0"} for i in range(4)]

        results = ParallelMigrator(manager, max_workers=2).migrate(
            data, "1.0.0", "2.0.0"
        )
        assert len(results) == 4
        assert all(r.email.endswith("@test.com") for r in results)

    def test_parallel_empty_input(self) -> None:
        manager = _setup_two_version_manager()

        from .migration.strategies import ParallelMigrator

        results = ParallelMigrator(manager).migrate([], "1.0.0", "2.0.0")
        assert results == []
