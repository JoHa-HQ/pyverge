"""Tests for target resolver factories."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

import pytest
import semver
from pydantic import BaseModel

from pyverge.migration import (
    DiscoverySettings,
    PydanticModelAdapter,
    Registry,
    RegistryError,
    VersionNode,
    earliest_target_resolver,
    fixed_target_resolver,
    latest_target_resolver,
    multi_target_resolver,
    skip_target_resolver,
)
from tests.examples.pydantic.semver_nested import (
    AddressV1,
    AddressV3,
    PersonV1,
    PersonV2,
)
from tests.utils import envelope_model


@pytest.mark.parametrize(
    "populated_registry",
    [
        (semver.Version, (PersonV1, PersonV2, AddressV1, AddressV3)),
    ],
    indirect=True,
)
class TestResolverFactories:
    """Tests for package-level resolver factories."""

    @pytest.mark.parametrize(
        ("source_cls", "factory", "expected"),
        [
            pytest.param(
                PersonV1,
                lambda reg, _adapter, _settings: latest_target_resolver(reg),
                ("Person", semver.VersionInfo(2, 0, 0)),
                id="latest",
            ),
            pytest.param(
                AddressV3,
                lambda reg, _adapter, _settings: earliest_target_resolver(reg),
                ("Address", semver.VersionInfo(1, 0, 0)),
                id="earliest",
            ),
            pytest.param(
                PersonV1,
                lambda reg, _adapter, _settings: skip_target_resolver(reg),
                None,
                id="skip",
            ),
            pytest.param(
                PersonV1,
                lambda reg, adapter, settings: fixed_target_resolver(
                    reg,
                    envelope_model(adapter, settings, PersonV2),
                ),
                "target",
                id="fixed",
            ),
        ],
    )
    def test_resolver_factory(  # noqa: PLR0913
        self,
        populated_registry: Registry[semver.Version, BaseModel],
        model_adapter: PydanticModelAdapter,
        discovery_settings: DiscoverySettings,
        source_cls: type[BaseModel],
        factory: Callable[
            [
                Registry[semver.Version, BaseModel],
                PydanticModelAdapter,
                DiscoverySettings,
            ],
            Any,
        ],
        expected: tuple[str, semver.VersionInfo] | None | Literal["target"],
    ) -> None:
        source = envelope_model(model_adapter, discovery_settings, source_cls)
        resolver = factory(populated_registry, model_adapter, discovery_settings)
        target = resolver(source)

        if expected is None:
            assert target is None
        elif expected == "target":
            target_node = envelope_model(model_adapter, discovery_settings, PersonV2)
            assert target == target_node
        else:
            assert target is not None
            assert target.version == expected

    def test_fixed_target_resolver_wrong_kind_raises(
        self,
        populated_registry: Registry[semver.Version, BaseModel],
        model_adapter: PydanticModelAdapter,
        discovery_settings: DiscoverySettings,
    ) -> None:
        source = envelope_model(model_adapter, discovery_settings, AddressV1)
        target_node = envelope_model(model_adapter, discovery_settings, PersonV2)
        resolver = fixed_target_resolver(populated_registry, target_node)
        with pytest.raises(RegistryError):
            resolver(source)

    def test_fixed_target_resolver_rejects_unregistered_target(
        self,
        populated_registry: Registry[semver.Version, BaseModel],
        model_adapter: PydanticModelAdapter,
        discovery_settings: DiscoverySettings,
    ) -> None:
        unregistered = VersionNode(
            _model=PersonV2,
            _value=semver.VersionInfo(9, 9, 9),
            _kind="Person",
        )
        with pytest.raises(RegistryError):
            fixed_target_resolver(populated_registry, unregistered)

    def test_multi_target_resolver_uses_wildcard_fallback(
        self,
        populated_registry: Registry[semver.Version, BaseModel],
        model_adapter: PydanticModelAdapter,
        discovery_settings: DiscoverySettings,
    ) -> None:
        person_source = envelope_model(model_adapter, discovery_settings, PersonV1)
        address_source = envelope_model(model_adapter, discovery_settings, AddressV3)
        resolver = multi_target_resolver(
            {
                "Person": latest_target_resolver(populated_registry),
                "*": earliest_target_resolver(populated_registry),
            }
        )

        person_target = resolver(person_source)
        assert person_target is not None
        assert person_target.version == ("Person", semver.VersionInfo(2, 0, 0))

        address_target = resolver(address_source)
        assert address_target is not None
        assert address_target.version == ("Address", semver.VersionInfo(1, 0, 0))
