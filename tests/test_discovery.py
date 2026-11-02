# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""Diff discovery tests."""

from __future__ import annotations

import pytest

from pyverge.discovery.reflection import (
    CallableDiffDiscovery,
    JsonPatchDiffDiscovery,
)
from pyverge.migrations.json_patch import JsonPatch
from tests.examples.pydantic.semver import UserV1, UserV2


def _patch(*ops: dict) -> JsonPatch:
    return JsonPatch(list(ops))


def _callable_migration(data: dict, context=None) -> dict:
    data["added"] = 1
    data["nested"]["field"] = 2
    del data["removed"]
    return {**data, "returned": 3}


@pytest.mark.parametrize(
    "discovery, migration, added, removed, modified",
    [
        pytest.param(
            JsonPatchDiffDiscovery(),
            _patch(
                {"op": "add", "path": "/added", "value": 1},
                {"op": "remove", "path": "/removed"},
                {"op": "replace", "path": "/changed", "value": 2},
                {"op": "move", "from": "/old", "path": "/new"},
                {"op": "copy", "from": "/source", "path": "/copy"},
                {"op": "add", "path": "/nested/field", "value": 3},
                {"op": "add", "path": "", "value": 4},
            ),
            {"added", "new", "copy", "nested"},
            {"removed", "old", "source"},
            {"changed"},
            id="json-patch",
        ),
        pytest.param(
            CallableDiffDiscovery(),
            _callable_migration,
            {"added", "returned"},
            {"removed"},
            {"nested"},
            id="callable",
        ),
    ],
)
def test_diff_discovery(  # noqa: PLR0913, PLR0917
    discovery, migration, added, removed, modified, model_adapter
) -> None:
    diff = discovery.discover(
        migration,
        model_adapter.versionable(UserV1),
        model_adapter.versionable(UserV2),
    )

    assert diff.origin == "migration"
    assert set(diff.added_fields) == added
    assert set(diff.removed_fields) == removed
    assert set(diff.modified_fields) == modified
