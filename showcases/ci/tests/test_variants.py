from __future__ import annotations

import pytest
from variants import (
    build_billing_manager,
    build_chain_manager,
    build_declarative_manager,
    build_key_only_registry,
    build_orders_manager,
)
from variants.key_only import add_size
from variants.widget_models import WidgetV1, WidgetV2

from pyverge.graph import GraphBuilder
from pyverge.jgf import JgfExporter
from pyverge.registry.errors import MigrationPathError
from pyverge.versioning import (
    MigrationDescriptor,
    VersionEdge,
    default_content_hasher,
)


def test_chain_variant_supports_forward_and_reverse() -> None:
    manager = build_chain_manager()
    payload = {"kind": "Item", "version": "1.0.0", "name": "widget"}

    latest = manager.runner().run(payload, "latest")
    earliest = manager.runner().run(latest, "earliest")
    pinned = manager.runner().run(payload, "2.0.0")

    assert latest["version"] == "3.0.0"
    assert latest["currency"] == "EUR"
    assert earliest["version"] == "1.0.0"
    assert "price" not in earliest
    assert pinned["version"] == "2.0.0"


def test_declarative_variant_uses_json_patch_and_jsonata() -> None:
    manager = build_declarative_manager()
    result = manager.runner().run(
        {"kind": "User", "version": "1.0.0", "name": "Alice"},
        "latest",
    )

    assert result == {
        "kind": "User",
        "version": "3.0.0",
        "name": "Alice",
        "age": 0,
        "status": "active",
    }


def test_namespace_variant_isolates_identity_and_export() -> None:
    orders = build_orders_manager()
    billing = build_billing_manager()

    assert orders.get("Account", "1.0.0").namespace == "com.acme.orders"
    assert billing.get("Account", "1.0.0").namespace == "com.acme.billing"

    exported = JgfExporter(default_content_hasher()).export_graph(
        GraphBuilder().build(orders.registry)
    )
    assert exported.nodes[0].id == "com.acme.orders:Account@1.0.0"


def test_key_only_graph_contains_topology_without_models() -> None:
    registry, _adapter, source_key, target_key = build_key_only_registry()
    graph = GraphBuilder().build(registry)

    assert graph.has_entry(source_key)
    assert graph.has_entry(target_key)
    assert graph.find_model(source_key) is None
    assert graph.find_model(target_key) is None
    assert graph.versions == []
    assert graph.migrations("Widget") == []
    with pytest.raises(MigrationPathError):
        graph.migration_path(source_key, target_key)


def test_key_only_graph_hydrates_and_binds_before_execution() -> None:
    registry, adapter, source_key, target_key = build_key_only_registry()

    source = adapter.versionable(WidgetV1)
    target = adapter.versionable(WidgetV2)
    registry.hydrate(source)
    registry.hydrate(target)
    registry.store_migration(
        VersionEdge(
            source=source,
            target=target,
            diff=adapter.diff(source, target),
            func=add_size,
            migration=MigrationDescriptor(
                strategy="callable",
                identity="variants.key_only.add_size",
            ),
        )
    )

    hydrated = GraphBuilder().build(registry)
    assert hydrated.get_model(source_key) is source
    assert hydrated.get_model(target_key) is target
    assert hydrated.migration_path(source, target) == [(source, target)]
