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

from dataclasses import dataclass
from typing import Any

import pytest
from fastmcp_demo.domain import ALL_VERSIONS, V1, V2, V3
from pydantic import create_model

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


@dataclass(frozen=True)
class Hop:
    """One leg of the walk: the version visited and the typed result."""

    version: str
    container: type
    payload: dict


def walk_topology(manager: Any, kind: str, versions: tuple[str, ...]) -> list[Hop]:
    """Walk *versions* newest -> oldest -> newest, validating every hop.

    Returns the down-walk hops; each payload is validated through ``container=``
    so a schema mismatch raises instead of passing silently. The return trip
    proves the reverse edges exist and are idempotent.
    """
    newest = versions[-1]
    newest_cls = manager.get(kind, newest).model
    start = newest_cls.model_validate(
        {"kind": kind, "version": newest, "city": "Berlin"}
    )

    hops: list[Hop] = []
    for version in reversed(versions):
        cls = manager.get(kind, version).model
        result = manager.migrate(
            start.model_dump(mode="json"), target=version, container=cls
        )
        assert isinstance(result, cls), f"{version} did not yield {cls.__name__}"
        hops.append(Hop(version, cls, result.model_dump(mode="json")))

    back = manager.migrate(hops[-1].payload, target=newest, container=newest_cls)
    assert isinstance(back, newest_cls), (
        f"return trip did not yield {newest_cls.__name__}"
    )
    return hops


def _hop(manager, version: str) -> Hop:
    return next(
        h for h in walk_topology(manager, KIND, ALL_VERSIONS) if h.version == version
    )


class TestTopologyWalk:
    @pytest.mark.parametrize("version", ALL_VERSIONS, ids=ALL_VERSIONS)
    def test_hop_is_typed(self, manager, version: str) -> None:
        """Every hop validates against its version's model via ``container=``."""
        assert _hop(manager, version).container is manager.get(KIND, version).model

    @pytest.mark.parametrize(
        ("version", "surface"), VERSION_SURFACE.items(), ids=VERSION_SURFACE
    )
    def test_hop_exposes_version_field_surface(
        self, manager, version: str, surface: set[str]
    ) -> None:
        """The converged payload carries exactly the version's fields."""
        assert set(_hop(manager, version).payload) == surface

    def test_round_trip_visits_every_version(self, manager) -> None:
        hops = walk_topology(manager, KIND, ALL_VERSIONS)
        assert [hop.version for hop in hops] == [V3, V2, V1]


class TestTopologyGuards:
    def test_missing_reverse_edge_raises(self, manager) -> None:
        """A version with only a forward edge cannot be reached by the down-walk."""
        # v4 exists with a forward edge only — nothing migrates v4 back down.
        v4 = create_model(
            "SearchWeatherV4",
            kind=(str, KIND),
            version=(str, "4.0.0"),
            city=(str, ...),
            gust=(float, 0.0),
        )
        manager.store_model(v4)
        with pytest.raises(MigrationNotFoundError):
            walk_topology(manager, KIND, (V1, V3, "4.0.0"))
