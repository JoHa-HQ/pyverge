# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import Any

from pyverge.core.context import MigrationContext
from pyverge.core.types import (
    ModelData,
)


def _schema(kind: str, version: str, props: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": kind,
        "version": version,
        "type": "object",
        "properties": {
            "kind": {"type": "string", "default": kind},
            "version": {"type": "string", "default": version},
            **props,
        },
    }


USER_V1_0_0 = _schema("User", "1.0.0", {"name": {"type": "string"}})
USER_V1_2_3 = _schema("User", "1.2.3", {"name": {"type": "string"}})
USER_V2_0_0 = _schema(
    "User",
    "2.0.0",
    {"name": {"type": "string"}, "age": {"type": "integer"}},
)
USER_V3_0_0 = _schema(
    "User",
    "3.0.0",
    {
        "name": {"type": "string"},
        "age": {"type": "integer"},
        "status": {"type": "string", "default": "active"},
    },
)
USER_V2_0_0_BETA_1 = _schema("User", "2.0.0-beta.1", {"name": {"type": "string"}})
USER_V0_1_1_DEV_7 = _schema("User", "0.1.1+dev.7", {"name": {"type": "string"}})

USER_V2025_01_01 = _schema("User", "2025-01-01", {"name": {"type": "string"}})
USER_V2025_03_10 = _schema("User", "2025-03-10", {"name": {"type": "string"}})
USER_V2025_12_31 = _schema("User", "2025-12-31", {"name": {"type": "string"}})
USER_V2026_02_28 = _schema("User", "2026-02-28", {"name": {"type": "string"}})
USER_V2026_03_01 = _schema("User", "2026-03-01", {"name": {"type": "string"}})

ADDRESS_V1_0_0 = _schema("Address", "1.0.0", {"street": {"type": "string"}})
ADDRESS_V2_0_0 = _schema("Address", "2.0.0", {"street": {"type": "string"}})
ADDRESS_V3_0_0 = _schema("Address", "3.0.0", {"street": {"type": "string"}})


def _object(kind: str, version: str, props: dict[str, Any]) -> dict[str, Any]:
    """A pure object schema (no top-level identity keys) for ``definitions``."""
    return {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "default": kind},
            "version": {"type": "string", "default": version},
            **props,
        },
    }
