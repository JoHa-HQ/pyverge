"""Snapshot the field surface of every registered version.

A schema change is then a visible diff rather than a silent break. Each version
is snapshotted by name, so ``pytest --snapshot-update`` rewrites only the
version that changed. Mirrors the ``test_all_version_samples_match_snapshot``
pattern from the joha project.
"""

from __future__ import annotations

import pytest
from fastmcp_demo.domain import ALL_VERSIONS
from pydantic import BaseModel
from syrupy.assertion import SnapshotAssertion


def _field_surface(model: type[BaseModel]) -> dict[str, str]:
    """Return ``{field: annotation}`` for *model*, sorted by field name.

    Annotations are stringified so the snapshot is stable across Python/pydantic
    versions; identity fields are included so the version is fully captured.
    """
    return {
        name: str(field.annotation)
        for name, field in sorted(model.model_fields.items())
    }


@pytest.mark.parametrize("version", ALL_VERSIONS)
def test_version_field_surface_matches_snapshot(
    manager, version: str, snapshot: SnapshotAssertion
) -> None:
    model = manager.get("search_weather", version).model
    assert model is not None, f"{version} has no concrete model"
    assert _field_surface(model) == snapshot(name=f"search_weather@{version}")
