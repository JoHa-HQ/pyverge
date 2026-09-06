from __future__ import annotations

from typing import Any


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

INVALID_BETA = _schema("User", "beta.7", {"name": {"type": "string"}})
INVALID_ALPHA = _schema("User", "0.0.0.alpha7", {"name": {"type": "string"}})
INVALID_TIME = _schema("User", "15:15:20.000Z", {"name": {"type": "string"}})


MIGRATE_V1_TO_V2 = {
    "from": "1.0.0",
    "to": "2.0.0",
    "ops": [{"op": "add", "path": "/age", "value": None}],
}

MIGRATE_V2_TO_V3 = {
    "from": "2.0.0",
    "to": "3.0.0",
    "ops": [
        {"op": "set_default", "path": "/age", "value": 0},
        {"op": "set_default", "path": "/status", "value": "active"},
    ],
}

MIGRATE_ADDRESS_100_200 = {
    "from": "1.0.0",
    "to": "2.0.0",
    "ops": [
        {"op": "add", "path": "/country", "value": None},
        {"op": "add", "path": "/postal_code", "value": None},
    ],
}

MIGRATE_CONTACT_100_200 = {
    "from": "1.0.0",
    "to": "2.0.0",
    "ops": [
        {"op": "add", "path": "/email", "value": None},
        {"op": "add", "path": "/preferred", "value": "phone"},
    ],
}
