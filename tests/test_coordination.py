"""Tests for Coordinator pattern from examples/coordination.py."""

from tests.examples.coordination import (
    IssueContainer,
    ProjectContainer,
    UserContainer,
)


class TestCoordinatorAccess:
    """Test instance creation from Coordinator declaration."""

    def test_access_by_container_type(self, coordinator):
        """Coordinator subscript by container type returns a manager instance."""
        user_mgr = coordinator[UserContainer]
        assert user_mgr is not None
        assert user_mgr._version_property == "version"

    def test_access_by_forward_ref(self, coordinator):
        """Coordinator subscript by string returns a manager instance."""
        project_mgr = coordinator["ProjectContainer"]
        assert project_mgr is not None
        assert project_mgr._version_property == "schema_version"

    def test_per_manager_config_override(self, coordinator):
        """Per-manager config overrides defaults."""
        user_mgr = coordinator[UserContainer]
        project_mgr = coordinator[ProjectContainer]

        assert user_mgr._version_property == "version"  # from defaults
        assert project_mgr._version_property == "schema_version"  # per-manager override


class TestCoordinatorBatchOperations:
    """Test cross-cutting batch operations."""

    def test_validate_data(self, coordinator):
        """Validate data against registered models."""
        user_mgr = coordinator[UserContainer]

        user_data = {"version": "1.0.0", "username": "alice", "email": "a@x.com"}
        assert user_mgr.validate_data(user_data, "1.0.0") is True

    def test_all_migrations_pass(self, coordinator):
        """Test all migration paths complete without error."""
        results = coordinator.test_all_migrations()
        assert results.all_passed

    def test_dump_schemas(self, coordinator, tmp_path):
        """Dump all schemas to a directory."""
        coordinator.dump_schemas(str(tmp_path))
        assert len(list(tmp_path.iterdir())) > 0
