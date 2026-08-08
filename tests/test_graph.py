"""Tests for GraphBuilder and MigrationGraph (strict ``(kind, version)`` discovery)."""

from __future__ import annotations

from typing import Literal

import pendulum
import pytest
import semver
from pydantic import BaseModel

from pyverge.migration import (
    DiscoverySettings,
    GraphEntry,
    MaxDepthExceededError,
    PydanticModelAdapter,
    Registry,
    types,
)
from tests.examples.pydantic.chrono import UserV20250310, UserV20251231
from tests.examples.pydantic.chrono_nested import (
    AddressV20240101,
    ContactV20240101,
)
from tests.examples.pydantic.semver_nested import (
    AddressV1,
    AddressV2,
    ContactV1,
    PersonV1,
    PersonV2,
)
from tests.utils import (
    default_graph_builder,
    envelope_model,
    populate_graph,
    register_models,
)


def _latest_resolver(
    registry: Registry[types.VersionValue, BaseModel],
) -> types.TargetResolver:
    def resolve(kind: types.ModelKind, current: types.Versionable) -> types.Versionable:
        return registry.latest(kind)

    return resolve


def _fixed_resolver(
    target: types.Versionable,
) -> types.TargetResolver:
    def resolve(kind: types.ModelKind, current: types.Versionable) -> types.Versionable:
        return target

    return resolve


class TestGraphEntry:
    """``GraphEntry`` value object."""

    def test_holds_path_source_target(
        self,
        model_adapter: PydanticModelAdapter,
        discovery_settings: DiscoverySettings,
    ) -> None:
        source = envelope_model(model_adapter, discovery_settings, PersonV1)
        target = envelope_model(model_adapter, discovery_settings, PersonV2)

        entry = GraphEntry(path=("document",), source=source, target=target)

        assert entry.path == ("document",)
        assert entry.source is source
        assert entry.target is target
        assert entry.kind == "Person"

    def test_repr(
        self, model_adapter: PydanticModelAdapter, discovery_settings: DiscoverySettings
    ) -> None:
        source = envelope_model(model_adapter, discovery_settings, PersonV1)
        target = envelope_model(model_adapter, discovery_settings, PersonV2)

        entry = GraphEntry(path=("document",), source=source, target=target)

        assert "GraphEntry" in repr(entry)
        assert "document" in repr(entry)

    def test_holds_migration_steps(
        self,
        model_adapter: PydanticModelAdapter,
        discovery_settings: DiscoverySettings,
    ) -> None:
        source = envelope_model(model_adapter, discovery_settings, PersonV1)
        target = envelope_model(model_adapter, discovery_settings, PersonV2)
        steps = ((source, target),)

        entry = GraphEntry(
            path=("document",),
            source=source,
            target=target,
            steps=steps,
        )

        assert entry.steps == steps


class TestMigrationGraph:
    """Structural containment DAG operations."""

    @pytest.mark.parametrize(
        "registry, models, payload",
        [
            (
                Registry[semver.Version, BaseModel](),
                [PersonV1, PersonV2, AddressV1, ContactV1],
                {
                    "document": {
                        "kind": "Person",
                        "version": "1.0.0",
                        "name": "Alice",
                        "address": {
                            "kind": "Address",
                            "version": "1.0.0",
                            "street": "Main",
                            "city": "Paris",
                        },
                        "contacts": [
                            {
                                "kind": "Contact",
                                "version": "1.0.0",
                                "phone": "555-0100",
                            },
                            {
                                "kind": "Contact",
                                "version": "1.0.0",
                                "phone": "555-0200",
                            },
                        ],
                    }
                },
            ),
            (
                Registry[pendulum.Date, BaseModel](),
                [UserV20250310, UserV20251231, AddressV20240101, ContactV20240101],
                {
                    "document": {
                        "kind": "User",
                        "version": "2025-03-10",
                        "name": "Alice",
                        "address": {
                            "kind": "Address",
                            "version": "2024-01-01",
                            "street": "Main",
                            "city": "Paris",
                        },
                        "contacts": [
                            {
                                "kind": "Contact",
                                "version": "2024-01-01",
                                "phone": "555-0100",
                            },
                            {
                                "kind": "Contact",
                                "version": "2024-01-01",
                                "phone": "555-0200",
                            },
                        ],
                    }
                },
            ),
        ],
        ids=[
            "semver_topological_order_children_before_parents",
            "date_topological_order_children_before_parents",
        ],
    )
    def test_topological_order_children_before_parents(
        self,
        model_adapter: PydanticModelAdapter,
        discovery_settings: DiscoverySettings,
        registry: Registry[types.VersionValue, BaseModel],
        models: list[type[types.VModel]],
        payload: dict,
    ) -> None:
        graph = populate_graph(
            model_adapter,
            registry,
            discovery_settings,
            *models,
            payload=payload,
            resolver=_latest_resolver(registry),
        )
        order = graph.topological_order()
        paths = [e.path for e in order]

        parent_idx = paths.index(("document",))
        for child in {
            ("document", "address"),
            ("document", "contacts", 0),
            ("document", "contacts", 1),
        }:
            assert paths.index(child) < parent_idx

    @pytest.mark.parametrize(
        "registry, models, payload",
        [
            (
                Registry[semver.Version, BaseModel](),
                [PersonV1, AddressV1, ContactV1],
                {
                    "document": {
                        "kind": "Person",
                        "version": "1.0.0",
                        "name": "Alice",
                        "address": {
                            "kind": "Address",
                            "version": "1.0.0",
                            "street": "Main",
                            "city": "Paris",
                        },
                        "contacts": [
                            {
                                "kind": "Contact",
                                "version": "1.0.0",
                                "phone": "555-0100",
                            },
                        ],
                    }
                },
            ),
        ],
    )
    def test_execution_levels_leaves_first(
        self,
        model_adapter: PydanticModelAdapter,
        discovery_settings: DiscoverySettings,
        registry: Registry[types.VersionValue, BaseModel],
        models: list[type[types.VModel]],
        payload: dict,
    ) -> None:
        graph = populate_graph(
            model_adapter,
            registry,
            discovery_settings,
            *models,
            payload=payload,
            resolver=_latest_resolver(registry),
        )
        levels = graph.execution_levels()
        level_paths = [[e.path for e in level] for level in levels]

        # Leaves (deepest paths) run first.
        assert all(
            path in level_paths[0]
            for path in [("document", "address"), ("document", "contacts", 0)]
        )
        # Root runs last.
        assert level_paths[-1] == [("document",)]

    @pytest.mark.parametrize(
        "registry, models, payload, expected_roots",
        [
            (
                Registry[semver.Version, BaseModel](),
                [PersonV1, AddressV1],
                {
                    "person": {"kind": "Person", "version": "1.0.0", "name": "Alice"},
                    "location": {
                        "kind": "Address",
                        "version": "1.0.0",
                        "street": "Main",
                        "city": "Paris",
                    },
                },
                {("person",), ("location",)},
            ),
        ],
    )
    def test_independent_roots(
        self,
        model_adapter: PydanticModelAdapter,
        discovery_settings: DiscoverySettings,
        registry: Registry[types.VersionValue, BaseModel],
        models: list[type[types.VModel]],
        payload: dict[str, dict],
        expected_roots: set[tuple[str]],
    ) -> None:
        register_models(model_adapter, registry, discovery_settings, *models)

        builder = default_graph_builder(registry, discovery_settings, model_adapter)
        graph = builder.build(
            payload,
            target_resolver=_latest_resolver(registry),
        )

        roots = graph.independent_roots()
        assert {r.path for r in roots} == expected_roots

    @pytest.mark.parametrize(
        "registry, models, payload, entry_lookup, kind",
        [
            (
                Registry[semver.Version, BaseModel](),
                [PersonV1, AddressV1],
                {
                    "document": {
                        "kind": "Person",
                        "version": "1.0.0",
                        "name": "Alice",
                        "address": {
                            "kind": "Address",
                            "version": "1.0.0",
                            "street": "Main",
                            "city": "Paris",
                        },
                    }
                },
                ("document", "address"),
                "Address",
            )
        ],
    )
    def test_entry_at(
        self,
        model_adapter: PydanticModelAdapter,
        discovery_settings: DiscoverySettings,
        registry: semver.Version,
        models: list[type[types.VModel]],
        payload: dict,
        entry_lookup: tuple[str],
        kind: str,
    ) -> None:
        graph = populate_graph(
            model_adapter,
            registry,
            discovery_settings,
            *models,
            payload=payload,
            resolver=_latest_resolver(registry),
        )
        entry = graph.entry_at(entry_lookup)
        assert entry is not None
        assert entry.kind == kind

        assert graph.entry_at(("missing",)) is None

    @pytest.mark.parametrize(
        "registry, models, payload, entry_lookup",
        [
            (
                Registry[semver.Version, BaseModel](),
                [PersonV1, AddressV1],
                {
                    "document": {
                        "kind": "Person",
                        "version": "1.0.0",
                        "name": "Alice",
                        "address": {
                            "kind": "Address",
                            "version": "1.0.0",
                            "street": "Main",
                            "city": "Paris",
                        },
                    }
                },
                ("missing",),
            )
        ],
    )
    def test_missing_entry(
        self,
        model_adapter: PydanticModelAdapter,
        discovery_settings: DiscoverySettings,
        registry: semver.Version,
        models: list[type[types.VModel]],
        payload: dict,
        entry_lookup: tuple[str],
    ) -> None:
        graph = populate_graph(
            model_adapter,
            registry,
            discovery_settings,
            *models,
            payload=payload,
            resolver=_latest_resolver(registry),
        )
        entry = graph.entry_at(entry_lookup)
        assert entry is None


class TestGraphBuilder:
    """Discovery of versioned entries in nested payloads."""

    @pytest.mark.parametrize(
        ("settings", "registry"),
        [(DiscoverySettings(), semver.Version)],
        indirect=["registry"],
    )
    @pytest.mark.parametrize(
        ("payload", "label"),
        [
            ({}, "empty payload"),
            ({"name": "Alice", "address": {"street": "Main"}}, "non-versioned payload"),
        ],
    )
    def test_skipped_payloads(
        self,
        model_adapter: PydanticModelAdapter,
        settings: DiscoverySettings,
        registry: semver.Version,
        payload: dict,
        label: str,
    ) -> None:
        register_models(model_adapter, registry, settings, PersonV1)

        builder = default_graph_builder(registry, settings, model_adapter)
        graph = builder.build(payload, target_resolver=_latest_resolver(registry))

        assert len(graph) == 0, f"{label} should not produce entries"
        assert not graph, f"{label} graph should be falsy"

    @pytest.mark.parametrize(
        ("settings", "registry"),
        [(DiscoverySettings(), semver.Version)],
        indirect=["registry"],
    )
    def test_flat_versioned_entry(
        self,
        model_adapter: PydanticModelAdapter,
        settings: DiscoverySettings,
        registry: Registry[semver.Version, BaseModel],
    ) -> None:
        register_models(model_adapter, registry, settings, PersonV1, PersonV2)

        builder = default_graph_builder(registry, settings, model_adapter)
        graph = builder.build(
            {"kind": "Person", "version": "1.0.0", "name": "Alice"},
            target_resolver=_latest_resolver(registry),
        )

        assert len(graph) == 1
        entry = graph.entry_at(())
        assert entry is not None
        assert entry.kind == "Person"
        assert entry.target == envelope_model(model_adapter, settings, PersonV2)

    @pytest.mark.parametrize(
        ("settings", "registry"),
        [(DiscoverySettings(), semver.Version)],
        indirect=["registry"],
    )
    def test_entry_steps_resolved_from_source_to_target(
        self,
        model_adapter: PydanticModelAdapter,
        settings: DiscoverySettings,
        registry: Registry[semver.Version, BaseModel],
    ) -> None:
        register_models(model_adapter, registry, settings, PersonV1, PersonV2)

        builder = default_graph_builder(registry, settings, model_adapter)
        graph = builder.build(
            {"kind": "Person", "version": "1.0.0", "name": "Alice"},
            target_resolver=_latest_resolver(registry),
        )

        entry = graph.entry_at(())
        assert entry is not None
        assert entry.steps == ((entry.source, entry.target),)

    @pytest.mark.parametrize(
        ("settings", "registry"),
        [(DiscoverySettings(), semver.Version)],
        indirect=["registry"],
    )
    def test_nested_versioned_entries(
        self,
        model_adapter: PydanticModelAdapter,
        settings: DiscoverySettings,
        registry: semver.Version,
    ) -> None:
        register_models(
            model_adapter, registry, settings, PersonV1, PersonV2, AddressV1, AddressV2
        )

        builder = default_graph_builder(registry, settings, model_adapter)
        graph = builder.build(
            {
                "document": {
                    "kind": "Person",
                    "version": "1.0.0",
                    "name": "Alice",
                    "address": {
                        "kind": "Address",
                        "version": "1.0.0",
                        "street": "Main",
                        "city": "Paris",
                    },
                }
            },
            target_resolver=_latest_resolver(registry),
        )

        EXPECTED_ENTRIES = 2
        assert len(graph) == EXPECTED_ENTRIES
        assert graph.entry_at(("document",)) is not None
        assert graph.entry_at(("document", "address")) is not None

    @pytest.mark.parametrize(
        ("settings", "registry"),
        [(DiscoverySettings(), semver.Version)],
        indirect=["registry"],
    )
    def test_versioned_entries_in_lists(
        self,
        model_adapter: PydanticModelAdapter,
        settings: DiscoverySettings,
        registry: semver.Version,
    ) -> None:
        register_models(
            model_adapter, registry, settings, PersonV1, PersonV2, ContactV1
        )

        builder = default_graph_builder(registry, settings, model_adapter)
        graph = builder.build(
            {
                "document": {
                    "kind": "Person",
                    "version": "1.0.0",
                    "name": "Alice",
                    "contacts": [
                        {"kind": "Contact", "version": "1.0.0", "phone": "555-0100"},
                        {"kind": "Contact", "version": "1.0.0", "phone": "555-0200"},
                    ],
                }
            },
            target_resolver=_latest_resolver(registry),
        )

        EXPECTED_ENTRIES = 3
        assert len(graph) == EXPECTED_ENTRIES
        assert graph.entry_at(("document", "contacts", 0)) is not None
        assert graph.entry_at(("document", "contacts", 1)) is not None

    @pytest.mark.parametrize(
        ("settings", "registry"),
        [(DiscoverySettings(), semver.Version)],
        indirect=["registry"],
    )
    def test_unknown_version_skipped(
        self,
        model_adapter: PydanticModelAdapter,
        settings: DiscoverySettings,
        registry: semver.Version,
    ) -> None:
        register_models(model_adapter, registry, settings, PersonV1)

        builder = default_graph_builder(registry, settings, model_adapter)
        graph = builder.build(
            {
                "document": {
                    "kind": "Person",
                    "version": "1.0.0",
                    "name": "Alice",
                },
                "orphan": {
                    "kind": "Person",
                    "version": "99.0.0",
                    "name": "Bob",
                },
            },
            target_resolver=_latest_resolver(registry),
        )

        assert len(graph) == 1
        assert graph.entry_at(("document",)) is not None

    @pytest.mark.parametrize(
        ("settings", "registry"),
        [(DiscoverySettings(version_property="schema_version"), semver.Version)],
        indirect=["registry"],
    )
    def test_custom_property_names(
        self,
        settings: DiscoverySettings,
        registry: semver.Version,
    ) -> None:
        class _Item(BaseModel):
            name: str
            kind: Literal["Item"] = "Item"
            schema_version: Literal["1.0.0"] = "1.0.0"

        adapter = PydanticModelAdapter(
            version_property=settings.version_property,
            kind_property=settings.kind_property,
        )
        register_models(adapter, registry, settings, _Item)

        builder = default_graph_builder(registry, settings, adapter)
        graph = builder.build(
            {"doc": {"kind": "Item", "schema_version": "1.0.0", "name": "X"}},
            target_resolver=_latest_resolver(registry),
        )

        assert len(graph) == 1
        assert graph.entry_at(("doc",)) is not None

    @pytest.mark.parametrize(
        ("settings", "registry"),
        [(DiscoverySettings(), semver.Version)],
        indirect=["registry"],
    )
    def test_mixed_versions_in_payload(
        self,
        model_adapter: PydanticModelAdapter,
        settings: DiscoverySettings,
        registry: semver.Version,
    ) -> None:
        register_models(
            model_adapter, registry, settings, PersonV1, PersonV2, AddressV1, AddressV2
        )

        builder = default_graph_builder(registry, settings, model_adapter)
        graph = builder.build(
            {
                "document": {
                    "kind": "Person",
                    "version": "1.0.0",
                    "name": "Alice",
                    "address": {
                        "kind": "Address",
                        "version": "2.0.0",
                        "street": "Main",
                        "city": "Paris",
                        "country": "FR",
                    },
                }
            },
            target_resolver=_latest_resolver(registry),
        )

        EXPECTED_ENTRIES = 2
        assert len(graph) == EXPECTED_ENTRIES
        person = graph.entry_at(("document",))
        address = graph.entry_at(("document", "address"))
        assert person is not None and str(person.source.version[1]) == "1.0.0"
        assert address is not None and str(address.source.version[1]) == "2.0.0"

    @pytest.mark.parametrize(
        ("settings", "registry", "expect_error"),
        [
            (
                DiscoverySettings(max_migration_depth=1),
                semver.Version,
                False,
            ),
            (
                DiscoverySettings(max_migration_depth=0),
                semver.Version,
                True,
            ),
        ],
        indirect=["registry"],
    )
    def test_max_migration_depth(
        self,
        model_adapter: PydanticModelAdapter,
        settings: DiscoverySettings,
        registry: semver.Version,
        expect_error: bool,
    ) -> None:
        """Versioned entries deeper than max_depth raise; within limit are accepted."""
        register_models(model_adapter, registry, settings, PersonV1, AddressV1)

        builder = default_graph_builder(registry, settings, model_adapter)
        payload = {
            "kind": "Person",
            "version": "1.0.0",
            "name": "Alice",
            "address": {
                "kind": "Address",
                "version": "1.0.0",
                "street": "Main",
                "city": "Paris",
            },
        }

        if expect_error:
            with pytest.raises(MaxDepthExceededError) as exc_info:
                builder.build(payload, target_resolver=_latest_resolver(registry))
            assert exc_info.value.kind == "Address"
            assert exc_info.value.max_depth == 0
        else:
            graph = builder.build(payload, target_resolver=_latest_resolver(registry))
            EXPECTED_ENTRIES = 2
            assert len(graph) == EXPECTED_ENTRIES
            assert graph.entry_at(()) is not None
            assert graph.entry_at(("address",)) is not None

    @pytest.mark.parametrize(
        ("settings", "registry"),
        [(DiscoverySettings(max_migration_depth=-1), semver.Version)],
        indirect=["registry"],
    )
    def test_max_depth_override_per_call(
        self,
        model_adapter: PydanticModelAdapter,
        settings: DiscoverySettings,
        registry: semver.Version,
    ) -> None:
        """max_depth can be overridden at build time independently of settings."""
        register_models(model_adapter, registry, settings, PersonV1, AddressV1)

        builder = default_graph_builder(registry, settings, model_adapter)
        payload = {
            "kind": "Person",
            "version": "1.0.0",
            "name": "Alice",
            "address": {
                "kind": "Address",
                "version": "1.0.0",
                "street": "Main",
                "city": "Paris",
            },
        }

        unlimited = builder.build(payload, target_resolver=_latest_resolver(registry))
        assert unlimited.entry_at(("address",)) is not None

        # Per-call override to 0 raises because the nested Address is beyond it.
        with pytest.raises(MaxDepthExceededError):
            builder.build(
                payload, target_resolver=_latest_resolver(registry), max_depth=0
            )

    @pytest.mark.parametrize(
        ("settings", "registry"),
        [(DiscoverySettings(), semver.Version)],
        indirect=["registry"],
    )
    def test_target_resolver_maps_per_kind(
        self,
        model_adapter: PydanticModelAdapter,
        settings: DiscoverySettings,
        registry: semver.Version,
    ) -> None:
        register_models(
            model_adapter, registry, settings, PersonV1, PersonV2, AddressV1, AddressV2
        )

        builder = default_graph_builder(registry, settings, model_adapter)
        graph = builder.build(
            {
                "document": {
                    "kind": "Person",
                    "version": "1.0.0",
                    "name": "Alice",
                    "address": {
                        "kind": "Address",
                        "version": "1.0.0",
                        "street": "Main",
                        "city": "Paris",
                    },
                }
            },
            target_resolver=_fixed_resolver(
                envelope_model(model_adapter, settings, PersonV2)
            ),
        )

        person = graph.entry_at(("document",))
        assert person is not None
        assert person.target == envelope_model(model_adapter, settings, PersonV2)
        # Resolver ignored kind and returned Person for Address too — allowed.
        address = graph.entry_at(("document", "address"))
        assert address is not None
        assert address.target == envelope_model(model_adapter, settings, PersonV2)
