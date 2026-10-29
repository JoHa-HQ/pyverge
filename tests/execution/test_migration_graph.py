from __future__ import annotations

import semver

from pyverge.execution import MigrationGraph
from pyverge.registry import Registry
from pyverge.schemas import ModelCodec, PydanticModelAdapter
from pyverge.settings import VersioningSettings
from pyverge.versioning import VersionKey, default_content_hasher
from tests.examples.pydantic.semver import UserV1, UserV2, migrate_v1_to_v2
from tests.utils.engine import edge_from_models


def test_migration_graph_snapshots_catalog() -> None:
    adapter = PydanticModelAdapter(
        codec=ModelCodec(
            namespace="",
            version_property="version",
            kind_property="kind",
        )
    )
    registry = Registry(namespace="", hasher=default_content_hasher())
    source = adapter.versionable(UserV1)
    target = adapter.versionable(UserV2)
    registry.store(source)
    registry.store(target)
    edge = edge_from_models(
        adapter,
        VersioningSettings(),
        UserV1,
        UserV2,
        func=migrate_v1_to_v2,
    )
    registry.store_migration(edge)

    graph = MigrationGraph.from_catalog(registry)

    assert graph.versions == [source, target]
    assert graph.get_model(source) is source
    assert graph.migrations("User") == [edge]
    assert graph.migration_path(source, target) == [(source, target)]


def test_migration_graph_snapshots_key_only_entries() -> None:
    registry = Registry(namespace="", hasher=default_content_hasher())
    key = VersionKey(namespace="", kind="User", version=semver.Version(1, 0, 0))
    registry.store(key)

    graph = MigrationGraph.from_catalog(registry)

    assert graph.entries[0] == key
    assert graph.has_entry(key)
    assert not graph.has_model(key)
