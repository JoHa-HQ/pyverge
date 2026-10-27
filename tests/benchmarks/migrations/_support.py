from __future__ import annotations

from typing import Any

import semver
from pydantic import create_model

from pyverge import Manager
from pyverge.schemas import ModelCodec, PydanticModelAdapter
from pyverge.types import ManagerMigrationKey


def build_chain(versions: int = 10, fields: int = 5) -> Manager[semver.Version]:
    manager_cls = Manager[semver.Version].configure(
        PydanticModelAdapter[semver.Version](codec=ModelCodec())
    )
    base = {f"f{i}": (str, "") for i in range(fields)}
    for version in range(versions):
        extra = {f"f{fields + i}": (str, "") for i in range(version)}
        definitions: dict[str, Any] = {}
        definitions.update(base)
        definitions.update(extra)
        model = create_model(
            f"UserV{version}",
            kind=(str, "User"),
            version=(str, f"{version}.0.0"),
            **definitions,
        )
        manager_cls.store_model(model)

    for version in range(versions - 1):

        def migrate(data, context=None, version=version):
            data = dict(data)
            data["version"] = f"{version + 1}.0.0"
            data[f"f{fields + version}"] = ""
            return data

        setattr(migrate, "__migration_id__", f"bench.chain.{version}")
        manager_cls.store_migration(
            ManagerMigrationKey(
                "User",
                f"{version}.0.0",
                f"{version + 1}.0.0",
            ),
            migrate,
        )
    return manager_cls()


def payload(fields: int = 5) -> dict[str, str]:
    return {
        "kind": "User",
        "version": "0.0.0",
        **{f"f{i}": "" for i in range(fields)},
    }
