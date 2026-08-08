"""Tests for Executor implementations."""

from __future__ import annotations

import pytest
import semver

from pyverge.migration import (
    DefaultEntryMigration,
    DiscoverySettings,
    Engine,
    LevelParallelExecutor,
    MigrationError,
    MigrationNotFoundError,
    MigrationSettings,
    PydanticDiff,
    PydanticModelAdapter,
    Registry,
    SequentialExecutor,
    StepExecutor,
    VersionEdge,
    types,
)
from tests.examples.pydantic.semver_nested import (
    AddressV1,
    AddressV2,
    ContactV1,
    ContactV2,
    PersonV1,
    PersonV2,
    migrate_address_100_200,
    migrate_contact_100_200,
)
from tests.utils import (
    default_graph_builder,
    envelope_model,
    make_engine,
    register_models,
)


def _latest_resolver(
    registry: Registry[types.VersionValue],
) -> types.TargetResolver:
    def resolve(kind: types.ModelKind, current: types.Versionable) -> types.Versionable:
        return registry.latest(kind)

    return resolve


def _preserve_children_person(data: dict) -> dict:
    """PersonV1 -> PersonV2 migration that keeps already-migrated child data."""
    data.setdefault("email", None)
    data.setdefault("contacts", [])
    return data


def _make_engine(
    model_adapter: PydanticModelAdapter,
    registry: Registry[semver.Version],
    discovery: DiscoverySettings,
    executor: types.Executor | None = None,
) -> Engine[semver.Version]:
    register_models(
        model_adapter, registry, discovery, PersonV1, PersonV2, AddressV1, AddressV2
    )
    register_models(model_adapter, registry, discovery, ContactV1, ContactV2)

    eng = Engine(
        registry,
        MigrationSettings(),
        executor or SequentialExecutor(),
        default_graph_builder(registry, discovery, model_adapter),
        model_adapter,
        DefaultEntryMigration(),
    )
    eng.store_migration(
        (
            envelope_model(model_adapter, discovery, PersonV1),
            envelope_model(model_adapter, discovery, PersonV2),
        ),
        _preserve_children_person,
    )
    eng.store_migration(
        (
            envelope_model(model_adapter, discovery, AddressV1),
            envelope_model(model_adapter, discovery, AddressV2),
        ),
        migrate_address_100_200,
    )
    eng.store_migration(
        (
            envelope_model(model_adapter, discovery, ContactV1),
            envelope_model(model_adapter, discovery, ContactV2),
        ),
        migrate_contact_100_200,
    )
    return eng


@pytest.mark.parametrize("executor", [SequentialExecutor(), LevelParallelExecutor()])
@pytest.mark.parametrize("registry", [semver.Version], indirect=True)
@pytest.mark.parametrize("discovery", [DiscoverySettings()])
def test_executor_returns_new_payload(
    model_adapter: PydanticModelAdapter,
    executor: types.Executor,
    registry: Registry[semver.Version],
    discovery: DiscoverySettings,
) -> None:
    eng = _make_engine(model_adapter, registry, discovery, executor=executor)
    payload = {
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
                {"kind": "Contact", "version": "1.0.0", "phone": "555-0100"},
            ],
        }
    }

    result = eng.migrate(payload)

    # Original payload is untouched
    assert payload["document"]["version"] == "1.0.0"
    assert "email" not in payload["document"]

    # Migrated copy has latest versions and added defaults.
    # The parent Person migration preserves already-migrated contacts.
    assert result["document"]["version"] == "2.0.0"
    assert result["document"]["email"] is None
    assert result["document"]["contacts"][0]["version"] == "2.0.0"
    assert result["document"]["contacts"][0]["email"] is None
    assert result["document"]["contacts"][0]["preferred"] == "phone"
    assert result["document"]["address"]["version"] == "2.0.0"
    assert result["document"]["address"]["country"] is None


@pytest.mark.parametrize("executor", [SequentialExecutor(), LevelParallelExecutor()])
@pytest.mark.parametrize("registry", [semver.Version], indirect=True)
@pytest.mark.parametrize("discovery", [DiscoverySettings()])
def test_executor_noop_when_source_is_target(
    model_adapter: PydanticModelAdapter,
    executor: types.Executor,
    registry: Registry[semver.Version],
    discovery: DiscoverySettings,
) -> None:
    eng = _make_engine(model_adapter, registry, discovery, executor=executor)
    payload = {
        "document": {
            "kind": "Person",
            "version": "2.0.0",
            "name": "Alice",
            "email": "a@example.com",
            "address": {
                "kind": "Address",
                "version": "2.0.0",
                "street": "Main",
                "city": "Paris",
                "country": "FR",
            },
            "contacts": [
                {
                    "kind": "Contact",
                    "version": "2.0.0",
                    "phone": "555-0100",
                    "preferred": "phone",
                },
            ],
        }
    }

    result = eng.migrate(payload)

    assert result["document"]["version"] == "2.0.0"
    assert result["document"]["address"]["version"] == "2.0.0"
    assert result["document"]["contacts"][0]["version"] == "2.0.0"


class TestStepExecutor:
    """StepExecutor resolves and runs a single migration edge."""

    @pytest.mark.parametrize("registry", [semver.Version], indirect=True)
    def test_execute_step_runs_registered_migration_and_updates_version(
        self,
        model_adapter: PydanticModelAdapter,
        discovery_settings: DiscoverySettings,
        registry: Registry[semver.Version],
    ) -> None:
        register_models(model_adapter, registry, discovery_settings, PersonV1, PersonV2)

        edge = VersionEdge(
            diff=PydanticDiff.from_pair(
                source=envelope_model(model_adapter, discovery_settings, PersonV1),
                target=envelope_model(model_adapter, discovery_settings, PersonV2),
            ),
            func=lambda d: {"version": "2.0.0", "name": d.get("name")},
        )
        registry.store_migration(edge)
        source = envelope_model(model_adapter, discovery_settings, PersonV1)
        target = envelope_model(model_adapter, discovery_settings, PersonV2)

        step_executor = StepExecutor(registry)
        result = step_executor.execute_step(
            source, target, {"version": "1.0.0", "name": "Alice"}, (), "version"
        )

        assert result == {"version": "2.0.0", "name": "Alice"}

    @pytest.mark.parametrize("registry", [semver.Version], indirect=True)
    def test_execute_step_raises_when_migration_missing(
        self,
        model_adapter: PydanticModelAdapter,
        discovery_settings: DiscoverySettings,
        registry: Registry[semver.Version],
    ) -> None:
        register_models(model_adapter, registry, discovery_settings, PersonV1, PersonV2)
        source = envelope_model(model_adapter, discovery_settings, PersonV1)
        target = envelope_model(model_adapter, discovery_settings, PersonV2)

        step_executor = StepExecutor(registry)
        with pytest.raises(MigrationNotFoundError):
            step_executor.execute_step(
                source, target, {"version": "1.0.0"}, (), "version"
            )


@pytest.mark.parametrize("registry", [semver.Version], indirect=True)
@pytest.mark.parametrize("discovery", [DiscoverySettings()])
def test_sequential_executor_runs_in_topological_order(
    model_adapter: PydanticModelAdapter,
    registry: Registry[semver.Version],
    discovery: DiscoverySettings,
) -> None:
    register_models(
        model_adapter, registry, discovery, PersonV1, PersonV2, AddressV1, AddressV2
    )

    order: list[str] = []

    def _track_person(data: dict) -> dict:
        order.append("person")
        return _preserve_children_person(data)

    def _track_address(data: dict) -> dict:
        order.append("address")
        return migrate_address_100_200(data)

    eng = make_engine(registry, MigrationSettings())
    eng.store_migration(
        (
            envelope_model(model_adapter, discovery, PersonV1),
            envelope_model(model_adapter, discovery, PersonV2),
        ),
        _track_person,
    )
    eng.store_migration(
        (
            envelope_model(model_adapter, discovery, AddressV1),
            envelope_model(model_adapter, discovery, AddressV2),
        ),
        _track_address,
    )

    payload = {
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
    }

    eng.migrate(payload)

    # Address is nested inside Person, so it must run before Person.
    assert order == ["address", "person"]


@pytest.mark.parametrize("registry", [semver.Version], indirect=True)
@pytest.mark.parametrize("discovery", [DiscoverySettings()])
def test_executor_propagates_migration_error(
    model_adapter: PydanticModelAdapter,
    registry: Registry[semver.Version],
    discovery: DiscoverySettings,
) -> None:
    register_models(model_adapter, registry, discovery, PersonV1, PersonV2)

    def _broken(data: dict) -> dict:
        raise RuntimeError("boom")

    eng = make_engine(registry, MigrationSettings())
    eng.store_migration(
        (
            envelope_model(model_adapter, discovery, PersonV1),
            envelope_model(model_adapter, discovery, PersonV2),
        ),
        _broken,
    )

    payload = {
        "document": {
            "kind": "Person",
            "version": "1.0.0",
            "name": "Alice",
        }
    }

    with pytest.raises(MigrationError, match="Migration failed"):
        eng.migrate(payload)


@pytest.mark.parametrize("registry", [semver.Version], indirect=True)
@pytest.mark.parametrize("discovery", [DiscoverySettings()])
def test_level_parallel_executor_single_entry_uses_no_pool(
    model_adapter: PydanticModelAdapter,
    registry: Registry[semver.Version],
    discovery: DiscoverySettings,
) -> None:
    """A graph with one entry per level should not require thread workers."""
    eng = _make_engine(
        model_adapter,
        registry,
        discovery,
        executor=LevelParallelExecutor(max_workers=2),
    )
    payload = {
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
    }

    result = eng.migrate(payload)
    assert result["document"]["version"] == "2.0.0"
    assert result["document"]["address"]["version"] == "2.0.0"
