"""Tests for target policy compilation."""

from __future__ import annotations

from typing import Any

import pytest
import semver
from pydantic import BaseModel

from pyverge.migration import (
    DiscoverySettings,
    MigrationSettings,
    ModelNotFoundError,
    PydanticModelAdapter,
    Registry,
    RegistryError,
    compile_target_resolver,
    compile_target_spec,
)
from tests.examples.pydantic.semver_nested import (
    AddressV1,
    AddressV2,
    AddressV3,
    PersonV1,
    PersonV2,
)
from tests.utils import envelope_model, register_models


@pytest.fixture
def adapter() -> PydanticModelAdapter:
    return PydanticModelAdapter(version_property="version", kind_property="kind")


@pytest.fixture
def settings() -> DiscoverySettings:
    return DiscoverySettings(version_property="version", kind_property="kind")


@pytest.fixture
def populated_registry(
    adapter: PydanticModelAdapter,
    settings: DiscoverySettings,
) -> Registry[semver.Version, BaseModel]:
    registry = Registry[semver.Version, BaseModel]()
    register_models(
        adapter,
        registry,
        settings,
        PersonV1,
        PersonV2,
        AddressV1,
        AddressV2,
        AddressV3,
    )
    return registry


class TestCompileTargetSpec:
    """Unit tests for compiling a single target spec into a resolver."""

    def test_skip_returns_none(
        self,
        populated_registry: Registry[semver.Version, BaseModel],
        adapter: PydanticModelAdapter,
        settings: DiscoverySettings,
    ) -> None:
        source = envelope_model(adapter, settings, PersonV1)
        resolver = compile_target_spec(
            populated_registry, "skip", version_property="version", adapter=adapter
        )
        assert resolver("Person", source) is None

    def test_latest_returns_highest_version(
        self,
        populated_registry: Registry[semver.Version, BaseModel],
        adapter: PydanticModelAdapter,
        settings: DiscoverySettings,
    ) -> None:
        source = envelope_model(adapter, settings, PersonV1)
        resolver = compile_target_spec(
            populated_registry, "latest", version_property="version", adapter=adapter
        )
        target = resolver("Person", source)
        assert target is not None
        assert target.version == ("Person", semver.VersionInfo(2, 0, 0))

    def test_earliest_returns_lowest_version(
        self,
        populated_registry: Registry[semver.Version, BaseModel],
        adapter: PydanticModelAdapter,
        settings: DiscoverySettings,
    ) -> None:
        source = envelope_model(adapter, settings, AddressV2)
        resolver = compile_target_spec(
            populated_registry, "earliest", version_property="version", adapter=adapter
        )
        target = resolver("Address", source)
        assert target is not None
        assert target.version == ("Address", semver.VersionInfo(1, 0, 0))

    def test_none_defaults_to_skip(
        self,
        populated_registry: Registry[semver.Version, BaseModel],
        adapter: PydanticModelAdapter,
        settings: DiscoverySettings,
    ) -> None:
        source = envelope_model(adapter, settings, PersonV1)
        resolver = compile_target_spec(
            populated_registry, None, version_property="version", adapter=adapter
        )
        assert resolver("Person", source) is None

    def test_model_class_resolves_to_registered_versionable(
        self,
        populated_registry: Registry[semver.Version, BaseModel],
        adapter: PydanticModelAdapter,
        settings: DiscoverySettings,
    ) -> None:
        source = envelope_model(adapter, settings, PersonV1)
        resolver = compile_target_spec(
            populated_registry, PersonV2, version_property="version", adapter=adapter
        )
        target = resolver("Person", source)
        assert target is not None
        assert target.version == ("Person", semver.VersionInfo(2, 0, 0))

    def test_versionable_target_used_as_is(
        self,
        populated_registry: Registry[semver.Version, BaseModel],
        adapter: PydanticModelAdapter,
        settings: DiscoverySettings,
    ) -> None:
        source = envelope_model(adapter, settings, PersonV1)
        target_node = envelope_model(adapter, settings, PersonV2)
        resolver = compile_target_spec(
            populated_registry,
            target_node,
            version_property="version",
            adapter=adapter,
        )
        assert resolver("Person", source) == target_node

    def test_unsupported_spec_raises(
        self,
        populated_registry: Registry[semver.Version, BaseModel],
        adapter: PydanticModelAdapter,
    ) -> None:
        with pytest.raises(RegistryError):
            compile_target_spec(
                populated_registry,
                "unknown",  # ty: ignore
                version_property="version",
                adapter=adapter,
            )

    def test_model_class_wrong_kind_raises(
        self,
        populated_registry: Registry[semver.Version, BaseModel],
        adapter: PydanticModelAdapter,
        settings: DiscoverySettings,
    ) -> None:
        source = envelope_model(adapter, settings, AddressV1)
        resolver = compile_target_spec(
            populated_registry, PersonV2, version_property="version", adapter=adapter
        )
        with pytest.raises(RegistryError):
            resolver("Address", source)


class TestCompileTargetResolver:
    """Integration tests for full policy compilation."""

    def test_global_latest(
        self,
        populated_registry: Registry[semver.Version, BaseModel],
        adapter: PydanticModelAdapter,
        settings: DiscoverySettings,
    ) -> None:
        source = envelope_model(adapter, settings, PersonV1)
        resolver = compile_target_resolver(
            populated_registry, "latest", adapter=adapter
        )
        target = resolver("Person", source)
        assert target is not None
        assert target.version == ("Person", semver.VersionInfo(2, 0, 0))

    def test_global_earliest(
        self,
        populated_registry: Registry[semver.Version, BaseModel],
        adapter: PydanticModelAdapter,
        settings: DiscoverySettings,
    ) -> None:
        source = envelope_model(adapter, settings, AddressV3)
        resolver = compile_target_resolver(
            populated_registry, "earliest", adapter=adapter
        )
        target = resolver("Address", source)
        assert target is not None
        assert target.version == ("Address", semver.VersionInfo(1, 0, 0))

    def test_global_skip(
        self,
        populated_registry: Registry[semver.Version, BaseModel],
        adapter: PydanticModelAdapter,
        settings: DiscoverySettings,
    ) -> None:
        source = envelope_model(adapter, settings, PersonV1)
        resolver = compile_target_resolver(populated_registry, "skip", adapter=adapter)
        assert resolver("Person", source) is None

    def test_per_kind_override_with_wildcard(
        self,
        populated_registry: Registry[semver.Version, BaseModel],
        adapter: PydanticModelAdapter,
        settings: DiscoverySettings,
    ) -> None:
        policy: dict[str, Any] = {
            "Person": "latest",
            "*": "earliest",
        }
        resolver = compile_target_resolver(populated_registry, policy, adapter=adapter)

        person_source = envelope_model(adapter, settings, PersonV1)
        person_target = resolver("Person", person_source)
        assert person_target is not None
        assert person_target.version == ("Person", semver.VersionInfo(2, 0, 0))

        address_source = envelope_model(adapter, settings, AddressV3)
        address_target = resolver("Address", address_source)
        assert address_target is not None
        assert address_target.version == ("Address", semver.VersionInfo(1, 0, 0))

    def test_per_kind_pinned_version_string(
        self,
        populated_registry: Registry[semver.Version, BaseModel],
        adapter: PydanticModelAdapter,
        settings: DiscoverySettings,
    ) -> None:
        policy: dict[str, Any] = {"Person": "1.0.0", "*": "latest"}
        resolver = compile_target_resolver(populated_registry, policy, adapter=adapter)

        person_source = envelope_model(adapter, settings, PersonV2)
        person_target = resolver("Person", person_source)
        assert person_target is not None
        assert person_target.version == ("Person", semver.VersionInfo(1, 0, 0))

        address_source = envelope_model(adapter, settings, AddressV1)
        address_target = resolver("Address", address_source)
        assert address_target is not None
        assert address_target.version == ("Address", semver.VersionInfo(3, 0, 0))

    def test_pinned_unregistered_version_raises(
        self,
        populated_registry: Registry[semver.Version, BaseModel],
        adapter: PydanticModelAdapter,
        settings: DiscoverySettings,
    ) -> None:
        resolver = compile_target_resolver(
            populated_registry, {"Person": "9.9.9"}, adapter=adapter  # ty: ignore
        )
        source = envelope_model(adapter, settings, PersonV1)
        with pytest.raises(ModelNotFoundError):
            resolver("Person", source)

    def test_per_kind_unknown_kind_uses_wildcard(
        self,
        populated_registry: Registry[semver.Version, BaseModel],
        adapter: PydanticModelAdapter,
        settings: DiscoverySettings,
    ) -> None:
        policy: dict[str, Any] = {
            "Person": "skip",
            "*": "latest",
        }
        resolver = compile_target_resolver(populated_registry, policy, adapter=adapter)
        address_source = envelope_model(adapter, settings, AddressV1)
        address_target = resolver("Address", address_source)
        assert address_target is not None
        assert address_target.version == ("Address", semver.VersionInfo(3, 0, 0))

    def test_per_kind_unknown_kind_without_wildcard_returns_none(
        self,
        populated_registry: Registry[semver.Version, BaseModel],
        adapter: PydanticModelAdapter,
        settings: DiscoverySettings,
    ) -> None:
        policy: dict[str, Any] = {"Person": "latest"}
        resolver = compile_target_resolver(populated_registry, policy, adapter=adapter)
        address_source = envelope_model(adapter, settings, AddressV1)
        assert resolver("Address", address_source) is None

    def test_settings_default_strategy(
        self,
        populated_registry: Registry[semver.Version, BaseModel],
        adapter: PydanticModelAdapter,
        settings: DiscoverySettings,
    ) -> None:
        migration_settings = MigrationSettings(
            version_property="version",
            kind_property="kind",
            target_strategy="latest",
        )
        source = envelope_model(adapter, settings, PersonV1)
        resolver = compile_target_resolver(
            populated_registry,
            migration_settings.target_strategy,
            adapter=adapter,
        )
        target = resolver("Person", source)
        assert target is not None
        assert target.version == ("Person", semver.VersionInfo(2, 0, 0))

    def test_unregistered_model_class_raises(
        self,
        adapter: PydanticModelAdapter,
        settings: DiscoverySettings,
    ) -> None:
        registry = Registry[semver.Version, BaseModel]()
        with pytest.raises(RegistryError):
            compile_target_resolver(registry, PersonV2, adapter=adapter)
