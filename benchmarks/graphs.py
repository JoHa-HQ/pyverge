"""Version graphs for benchmarks, built from the existing example models.

No new schemas: the graphs here mirror what the test suite already exercises, so
benchmarks stay hermetic and schema-rigorous.
"""

from __future__ import annotations

import semver

from pyverge import Manager
from pyverge.migration import (
    MigrationContext,
    MigrationSettings,
    PydanticModelAdapter,
)
from pyverge.types import ManagerMigrationKey
from tests.examples.pydantic.semver import (
    UserV1,
    UserV2,
    UserV3,
    migrate_v1_to_v2,
    migrate_v2_to_v3,
)


def _drop_age(data: dict, context: MigrationContext | None = None) -> dict:
    data = dict(data)
    data.pop("age", None)
    return data


def _drop_status(data: dict, context: MigrationContext | None = None) -> dict:
    data = dict(data)
    data.pop("status", None)
    return data


def user_manager() -> Manager[semver.Version]:
    """A linear ``User`` chain, both directions: v1 ↔ v2 ↔ v3.

    Reverse edges let a produce seam converge a returned ``latest`` (v3) payload
    down to a pinned older target.
    """
    user_manager_cls = Manager[semver.Version].configure(
        MigrationSettings(),
        PydanticModelAdapter(),
    )
    manager = user_manager_cls()
    manager.store_model(UserV1)
    manager.store_model(UserV2)
    manager.store_model(UserV3)
    manager.store_migration(
        ManagerMigrationKey("User", "1.0.0", "2.0.0"), migrate_v1_to_v2
    )
    manager.store_migration(
        ManagerMigrationKey("User", "2.0.0", "3.0.0"), migrate_v2_to_v3
    )
    manager.store_migration(ManagerMigrationKey("User", "2.0.0", "1.0.0"), _drop_age)
    manager.store_migration(ManagerMigrationKey("User", "3.0.0", "2.0.0"), _drop_status)
    return manager


__all__ = ["user_manager"]
