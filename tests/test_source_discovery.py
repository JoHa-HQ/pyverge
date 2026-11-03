# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio

import pytest
import semver

from pyverge import Manager
from pyverge.runtime.manager import (
    DiscoveredMigration,
    DiscoveredModel,
    ManagerMigrationKey,
)
from pyverge.schemas import PydanticModelAdapter
from tests.examples.pydantic.semver import UserV1, UserV2, migrate_v1_to_v2


class _Source:
    def accept(self, visitor) -> None:
        visitor.visit(DiscoveredModel(UserV1))
        visitor.visit(DiscoveredModel(UserV2))
        visitor.visit(
            DiscoveredMigration(
                ManagerMigrationKey("User", "1.0.0", "2.0.0"),
                migrate_v1_to_v2,
            )
        )


class _AsyncSource:
    async def accept(self, visitor) -> None:
        visitor.visit(DiscoveredModel(UserV1))
        visitor.visit(DiscoveredModel(UserV2))
        visitor.visit(
            DiscoveredMigration(
                ManagerMigrationKey("User", "1.0.0", "2.0.0"),
                migrate_v1_to_v2,
            )
        )


@pytest.mark.parametrize(
    ("model_adapter", "registry"),
    [[PydanticModelAdapter, [semver.Version, "test", [], []]]],
    indirect=["model_adapter", "registry"],
)
def test_manager_discover_registers_source(manager: type[Manager]) -> None:
    report = manager.discover(_Source())

    assert report.descriptors == 3  # noqa: PLR2004
    assert report.registered_models == 2  # noqa: PLR2004
    assert report.registered_migrations == 1
    assert manager().get("User", "1.0.0") is not None
    assert (
        manager().get_migration(ManagerMigrationKey("User", "1.0.0", "2.0.0"))
        is not None
    )


@pytest.mark.parametrize(
    ("model_adapter", "registry"),
    [[PydanticModelAdapter, [semver.Version, "test", [], []]]],
    indirect=["model_adapter", "registry"],
)
def test_manager_adiscover_registers_async_source(manager: type[Manager]) -> None:
    report = asyncio.run(manager.adiscover(_AsyncSource()))

    assert report.registered_models == 2  # noqa: PLR2004
    assert report.registered_migrations == 1


@pytest.mark.parametrize(
    ("model_adapter", "registry"),
    [[PydanticModelAdapter, [semver.Version, "test", [], []]]],
    indirect=["model_adapter", "registry"],
)
def test_manager_reflect_is_deprecated_discovery_alias(
    manager: type[Manager],
) -> None:
    with pytest.warns(DeprecationWarning):
        report = manager.reflect(_Source())

    assert report.registered_models == 2  # noqa: PLR2004
    assert report.registered_migrations == 1
