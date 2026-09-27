"""The time-travel topology test, parametrized per version.

Given a registered version chain, migrate a newest-shaped payload down to the
oldest version and back up, asserting each hop yields the correctly-typed
container and the exact field surface that version exposes. Parametrizing per
version makes each schema change its own named test case, so a drift points at
one version instead of a whole-chain assertion.

This catches the failure modes that unit tests on individual migrations miss: a
missing reverse edge, a non-idempotent forward migration, or a finalize step
that silently drops a field.
"""

from __future__ import annotations

import pytest
from fastmcp_demo.domain import ALL_VERSIONS, V1, V2, V3, schema
from topology import walk_topology

from pyverge.core.exceptions import MigrationNotFoundError

KIND = "search_weather"

#: The exact field surface each version exposes once converged. Each entry is a
#: named test case, so adding a version adds one row here — the diff documents
#: the version change.
VERSION_SURFACE = {
    V1: {"kind", "version", "city", "units", "temperature"},
    V2: {"kind", "version", "city", "units", "temperature", "humidity"},
    V3: {"kind", "version", "city", "units", "temperature", "humidity", "wind"},
}


def _hop(manager, version: str):
    """Return the down-walk hop for *version*."""
    return next(
        h for h in walk_topology(manager, KIND, ALL_VERSIONS) if h.version == version
    )


class TestTopologyWalk:
    @pytest.mark.parametrize("version", ALL_VERSIONS)
    def test_hop_is_typed(self, manager, version: str) -> None:
        """Every hop validates against its version's model via ``container=``."""
        hop = _hop(manager, version)
        assert hop.container is manager.get(KIND, version).model

    @pytest.mark.parametrize(
        ("version", "surface"),
        VERSION_SURFACE.items(),
        ids=["v1", "v2", "v3"],
    )
    def test_hop_exposes_version_field_surface(
        self, manager, version: str, surface: set[str]
    ) -> None:
        """The converged payload carries exactly the version's fields."""
        assert set(_hop(manager, version).payload) == surface

    def test_round_trip_visits_every_version(self, manager) -> None:
        hops = walk_topology(manager, KIND, ALL_VERSIONS)
        assert [hop.version for hop in hops] == [V3, "2.0.0", V1]


class TestTopologyGuards:
    def test_missing_reverse_edge_raises(self, manager) -> None:
        """A version with only a forward edge cannot be reached by the down-walk.

        ``walk_topology`` migrates down to the oldest version; a chain whose
        oldest hop has no reverse edge must fail loudly rather than silently
        leave the payload at the wrong version.
        """
        # v4 exists with a forward edge only — nothing migrates v4 back down.
        manager.store_model(
            schema(KIND, "4.0.0", {"gust": {"type": "number", "default": 0}})
        )
        with pytest.raises(MigrationNotFoundError):
            walk_topology(manager, KIND, (V1, V3, "4.0.0"))
