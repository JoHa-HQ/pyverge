# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""Declarative migration examples used by graph and migration tests."""

from __future__ import annotations

from pyverge.migrations import JsonataMigration, JsonPatchMigration

USER_JSONPATCH_V1_TO_V2 = JsonPatchMigration(
    {
        "from": "1.0.0",
        "to": "2.0.0",
        "ops": [{"op": "add", "path": "/age", "value": None}],
    }
)

USER_JSONATA_V2_TO_V3 = JsonataMigration.from_expression(
    '$merge([$, {"age": $coalesce(age, 0), "status": "active"}])'
)
