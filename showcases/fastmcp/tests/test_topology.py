"""The time-travel topology test.

Extracted from the joha project's ``test_migration_topology``: given a
registered version chain, migrate a newest-shaped payload down to the oldest
version and back up, asserting each hop yields the correctly-typed container.

This catches the failure modes that unit tests on individual migrations miss:
a missing reverse edge, a non-idempotent forward migration, or a finalize step
that silently drops a field.
"""

from __future__ import annotations

import pytest
from fastmcp_demo.application import walk_topology
from fastmcp_demo.domain import ALL_VERSIONS, V1, V3, schema

from pyverge.core.exceptions import MigrationNotFoundError


class TestTopologyWalk:
    def test_round_trip_visits_every_version(self, manager) -> None:
        hops = walk_topology(manager, "search_weather", ALL_VERSIONS)
        assert [hop.version for hop in hops] == [V3, "2.0.0", V1]

    def test_oldest_hop_loses_the_added_fields(self, manager) -> None:
        hops = walk_topology(manager, "search_weather", ALL_VERSIONS)
        oldest = hops[-1].payload
        assert "humidity" not in oldest
        assert "wind" not in oldest

    def test_newest_hop_keeps_the_added_fields(self, manager) -> None:
        hops = walk_topology(manager, "search_weather", ALL_VERSIONS)
        newest = hops[0].payload
        assert newest["humidity"] is False
        assert newest["wind"] == 0

    def test_each_hop_is_typed(self, manager) -> None:
        """Every hop validates against its version's model via ``container=``."""
        hops = walk_topology(manager, "search_weather", ALL_VERSIONS)
        for hop in hops:
            assert hop.container is manager.get("search_weather", hop.version).model


class TestTopologyGuards:
    def test_missing_reverse_edge_raises(self, manager) -> None:
        """A version with only a forward edge cannot be reached by the down-walk.

        ``walk_topology`` migrates down to the oldest version; a chain whose
        oldest hop has no reverse edge must fail loudly rather than silently
        leave the payload at the wrong version.
        """
        # v4 exists with a forward edge only — nothing migrates v4 back down.
        manager.store_model(
            schema(
                "search_weather", "4.0.0", {"gust": {"type": "number", "default": 0}}
            )
        )
        with pytest.raises(MigrationNotFoundError):
            walk_topology(manager, "search_weather", (V1, V3, "4.0.0"))
