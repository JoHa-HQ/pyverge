"""Tests for GraphBuilder and MigrationGraph (strict ``(kind, version)`` discovery)."""

from __future__ import annotations

from typing import Literal

import pendulum
import pytest
import semver
from pydantic import BaseModel

from pyverge import types
from pyverge.core import (
    DiscoverySettings,
    MaxDepthExceededError,
    MigrationSettings,
)
from pyverge.migration import (
    GraphEntry,
    MigrationGraph,
    PydanticModelAdapter,
    Registry,
    latest_target_resolver,
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
from tests.utils import envelope_model, register_models


class _Item(BaseModel):
    """Model registered under a custom ``schema_version`` property."""

    name: str
    kind: Literal["Item"] = "Item"
    schema_version: Literal["1.0.0"] = "1.0.0"


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
        "model_adapter, registry, migration_graph",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "test",
                    [PersonV1, PersonV2, AddressV1, ContactV1],
                    [],
                ],
                (
                    latest_target_resolver,
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
                id="semver_topological_order_children_before_parents",
            ),
            pytest.param(
                PydanticModelAdapter,
                [
                    pendulum.Date,
                    "test",
                    [UserV20250310, UserV20251231, AddressV20240101, ContactV20240101],
                    [],
                ],
                (
                    latest_target_resolver,
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
                id="date_topological_order_children_before_parents",
            ),
        ],
        indirect=["model_adapter", "registry", "migration_graph"],
    )
    def test_topological_order_children_before_parents(
        self,
        migration_graph: MigrationGraph[types.VersionValue],
    ) -> None:
        order = migration_graph.topological_order()
        paths = [e.path for e in order]

        parent_idx = paths.index(("document",))
        for child in {
            ("document", "address"),
            ("document", "contacts", 0),
            ("document", "contacts", 1),
        }:
            assert paths.index(child) < parent_idx

    @pytest.mark.parametrize(
        "model_adapter, registry, migration_graph",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [PersonV1, AddressV1, ContactV1], []],
                (
                    latest_target_resolver,
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
                id="semver_execution_levels_leaves_first",
            ),
        ],
        indirect=["model_adapter", "registry", "migration_graph"],
    )
    def test_execution_levels_leaves_first(
        self,
        migration_graph: MigrationGraph[types.VersionValue],
    ) -> None:
        levels = migration_graph.execution_levels()
        level_paths = [[e.path for e in level] for level in levels]

        # Leaves (deepest paths) run first.
        assert all(
            path in level_paths[0]
            for path in [("document", "address"), ("document", "contacts", 0)]
        )
        # Root runs last.
        assert level_paths[-1] == [("document",)]

    @pytest.mark.parametrize(
        "model_adapter, registry, migration_graph, expected_roots",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [PersonV1, AddressV1], []],
                (
                    latest_target_resolver,
                    {
                        "person": {
                            "kind": "Person",
                            "version": "1.0.0",
                            "name": "Alice",
                        },
                        "location": {
                            "kind": "Address",
                            "version": "1.0.0",
                            "street": "Main",
                            "city": "Paris",
                        },
                    },
                ),
                {("person",), ("location",)},
                id="semver_independent_roots",
            ),
        ],
        indirect=["model_adapter", "registry", "migration_graph"],
    )
    def test_independent_roots(
        self,
        migration_graph: MigrationGraph[types.VersionValue],
        expected_roots: set[tuple[str]],
    ) -> None:
        roots = migration_graph.independent_roots()
        assert {r.path for r in roots} == expected_roots

    @pytest.mark.parametrize(
        "model_adapter, registry, migration_graph, entry_lookup, kind",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [PersonV1, AddressV1], []],
                (
                    latest_target_resolver,
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
                ),
                ("document", "address"),
                "Address",
                id="semver_entry_at",
            ),
        ],
        indirect=["model_adapter", "registry", "migration_graph"],
    )
    def test_entry_at(
        self,
        migration_graph: MigrationGraph[types.VersionValue],
        entry_lookup: tuple[str],
        kind: str,
    ) -> None:
        entry = migration_graph.entry_at(entry_lookup)
        assert entry is not None
        assert entry.kind == kind

        assert migration_graph.entry_at(("missing",)) is None

    @pytest.mark.parametrize(
        "model_adapter, registry, migration_graph, entry_lookup",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [PersonV1, AddressV1], []],
                (
                    latest_target_resolver,
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
                ),
                ("missing",),
                id="semver_missing_entry",
            ),
        ],
        indirect=["model_adapter", "registry", "migration_graph"],
    )
    def test_missing_entry(
        self,
        migration_graph: MigrationGraph[types.VersionValue],
        entry_lookup: tuple[str],
    ) -> None:
        entry = migration_graph.entry_at(entry_lookup)
        assert entry is None


class TestGraphBuilder:
    """Discovery of versioned entries in nested payloads."""

    @pytest.mark.parametrize(
        ("payload", "label"),
        [
            pytest.param({}, "empty payload", id="empty"),
            pytest.param(
                {"name": "Alice", "address": {"street": "Main"}},
                "non-versioned payload",
                id="non_versioned",
            ),
        ],
    )
    @pytest.mark.parametrize(
        "model_adapter, registry",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [PersonV1], []],
                id="semver",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_skipped_payloads(
        self,
        graph_builder,
        registry: Registry[types.VersionValue],
        payload: dict,
        label: str,
    ) -> None:
        graph = graph_builder.build(
            payload, target_resolver=latest_target_resolver(registry)
        ).graph

        assert len(graph) == 0, f"{label} should not produce entries"
        assert not graph, f"{label} graph should be falsy"

    @pytest.mark.parametrize(
        "model_adapter, registry",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [PersonV1, PersonV2], []],
                id="semver_flat_versioned_entry",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_flat_versioned_entry(
        self,
        graph_builder,
        registry: Registry[types.VersionValue],
        model_adapter: PydanticModelAdapter,
        migration_settings: MigrationSettings,
    ) -> None:
        graph = graph_builder.build(
            {"kind": "Person", "version": "1.0.0", "name": "Alice"},
            target_resolver=latest_target_resolver(registry),
        ).graph

        assert len(graph) == 1
        entry = graph.entry_at(())
        assert entry is not None
        assert entry.kind == "Person"
        assert entry.target == envelope_model(
            model_adapter, migration_settings, PersonV2
        )

    @pytest.mark.parametrize(
        "model_adapter, registry",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [PersonV1, PersonV2], []],
                id="semver_entry_steps",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_entry_steps_resolved_from_source_to_target(
        self,
        graph_builder,
        registry: Registry[types.VersionValue],
    ) -> None:
        graph = graph_builder.build(
            {"kind": "Person", "version": "1.0.0", "name": "Alice"},
            target_resolver=latest_target_resolver(registry),
        ).graph

        entry = graph.entry_at(())
        assert entry is not None
        assert entry.steps == ((entry.source, entry.target),)

    @pytest.mark.parametrize(
        "model_adapter, registry, migration_graph, expected_entries",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "test",
                    [PersonV1, PersonV2, AddressV1, AddressV2],
                    [],
                ],
                (
                    latest_target_resolver,
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
                ),
                [(("document",), "1.0.0"), (("document", "address"), "1.0.0")],
                id="semver_nested_entries",
            ),
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [PersonV1, PersonV2, ContactV1], []],
                (
                    latest_target_resolver,
                    {
                        "document": {
                            "kind": "Person",
                            "version": "1.0.0",
                            "name": "Alice",
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
                [
                    (("document",), "1.0.0"),
                    (("document", "contacts", 0), "1.0.0"),
                    (("document", "contacts", 1), "1.0.0"),
                ],
                id="semver_entries_in_lists",
            ),
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [PersonV1], []],
                (
                    latest_target_resolver,
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
                ),
                [(("document",), "1.0.0")],
                id="semver_unknown_version",
            ),
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "test",
                    [PersonV1, PersonV2, AddressV1, AddressV2],
                    [],
                ],
                (
                    latest_target_resolver,
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
                ),
                [(("document",), "1.0.0"), (("document", "address"), "2.0.0")],
                id="semver_mixed_versions",
            ),
        ],
        indirect=["model_adapter", "registry", "migration_graph"],
    )
    def test_versioned_entries(
        self,
        migration_graph: MigrationGraph[types.VersionValue],
        expected_entries: list[tuple[tuple[str | int, ...], str]],
    ) -> None:
        assert len(migration_graph) == len(expected_entries)
        for path, version in expected_entries:
            entry = migration_graph.entry_at(path)
            assert entry is not None and str(entry.source.version[1]) == version

    @pytest.mark.parametrize(
        "migration_settings",
        [{"version_property": "schema_version"}],
        indirect=True,
    )
    @pytest.mark.parametrize(
        "model_adapter, registry",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [], []],
                id="custom_property_names",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_custom_property_names(
        self,
        graph_builder,
        registry: Registry[types.VersionValue],
        migration_settings: MigrationSettings,
    ) -> None:
        # The custom property name cannot be pre-registered through the shared
        # ``model_adapter``: the adapter must be rebuilt with the new property
        # before the model is stored.
        adapter = PydanticModelAdapter(
            version_property=migration_settings.version_property,
            kind_property=migration_settings.kind_property,
        )
        register_models(adapter, registry, migration_settings, _Item)

        graph = graph_builder.build(
            {"doc": {"kind": "Item", "schema_version": "1.0.0", "name": "X"}},
            target_resolver=latest_target_resolver(registry),
        ).graph

        assert len(graph) == 1
        assert graph.entry_at(("doc",)) is not None

    @pytest.mark.parametrize(
        "migration_settings",
        [{"max_migration_depth": 1}],
        indirect=True,
    )
    @pytest.mark.parametrize(
        "model_adapter, registry",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [PersonV1, AddressV1], []],
                id="semver_depth",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_max_migration_depth_within_limit(
        self,
        graph_builder,
        registry: Registry[types.VersionValue],
    ) -> None:
        """Entries at or within the configured max_depth are all accepted."""
        graph = graph_builder.build(
            {
                "kind": "Person",
                "version": "1.0.0",
                "name": "Alice",
                "address": {
                    "kind": "Address",
                    "version": "1.0.0",
                    "street": "Main",
                    "city": "Paris",
                },
            },
            target_resolver=latest_target_resolver(registry),
        ).graph

        EXPECTED_ENTRIES = 2
        assert len(graph) == EXPECTED_ENTRIES
        assert graph.entry_at(()) is not None
        assert graph.entry_at(("address",)) is not None

    @pytest.mark.parametrize(
        "migration_settings, build_depth",
        [
            pytest.param({"max_migration_depth": 0}, None, id="settings_depth_zero"),
            pytest.param({"max_migration_depth": -1}, 0, id="per_call_override_zero"),
        ],
        indirect=["migration_settings"],
    )
    @pytest.mark.parametrize(
        "model_adapter, registry",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [PersonV1, AddressV1], []],
                id="semver_depth",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_max_depth_exceeded(
        self,
        graph_builder,
        registry: Registry[types.VersionValue],
        build_depth: int | None,
    ) -> None:
        """A nested versioned entry beyond the active depth limit raises."""
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

        with pytest.raises(MaxDepthExceededError) as exc_info:
            graph_builder.build(
                payload,
                target_resolver=latest_target_resolver(registry),
                max_depth=build_depth,
            ).graph

        assert exc_info.value.kind == "Address"
        assert exc_info.value.max_depth == 0

    @pytest.mark.parametrize(
        "migration_settings",
        [{"max_migration_depth": 0}],
        indirect=True,
    )
    @pytest.mark.parametrize(
        "model_adapter, registry",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [PersonV1, AddressV1], []],
                id="semver_depth_override",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_max_depth_override_relaxes_limit(
        self,
        graph_builder,
        registry: Registry[types.VersionValue],
    ) -> None:
        """A per-call max_depth takes precedence over the configured limit."""
        graph = graph_builder.build(
            {
                "kind": "Person",
                "version": "1.0.0",
                "name": "Alice",
                "address": {
                    "kind": "Address",
                    "version": "1.0.0",
                    "street": "Main",
                    "city": "Paris",
                },
            },
            target_resolver=latest_target_resolver(registry),
            max_depth=1,
        ).graph

        EXPECTED_ENTRIES = 2
        assert len(graph) == EXPECTED_ENTRIES
        assert graph.entry_at(("address",)) is not None

    @pytest.mark.parametrize(
        "model_adapter, registry",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "test",
                    [PersonV1, PersonV2, AddressV1, AddressV2],
                    [],
                ],
                id="semver_target_resolver",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_custom_callable_target_resolver(
        self,
        graph_builder,
        model_adapter: PydanticModelAdapter,
        migration_settings: MigrationSettings,
    ) -> None:
        person_target = envelope_model(model_adapter, migration_settings, PersonV2)
        graph = graph_builder.build(
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
            target_resolver=lambda current: person_target,
        ).graph

        person = graph.entry_at(("document",))
        assert person is not None
        assert person.target == person_target
        # A callable resolver may ignore kind and return the same target for
        # every entry — graph builder allows arbitrary resolver behavior.
        address = graph.entry_at(("document", "address"))
        assert address is not None
        assert address.target == person_target
