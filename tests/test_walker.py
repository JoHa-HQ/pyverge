"""Tests for schema-aware walkers and end-to-end Engine migration."""

from __future__ import annotations

from typing import Any

import pendulum
import pytest
import semver

from pyverge.migration import (
    CompoundKeyWalker,
    DiscoverySettings,
    DiscoveryValidationError,
    Engine,
    MaxDepthExceededError,
    MigrationSettings,
    PydanticModelAdapter,
    PydanticWalker,
    Registry,
    types,
)
from tests.examples.pydantic.chrono import (
    UserV20250310,
    UserV20251231,
)
from tests.examples.pydantic.chrono import (
    migrate_v1_to_v2 as migrate_chrono_v1_to_v2,
)
from tests.examples.pydantic.semver import (
    UserContainer,
    UserV1,
    UserV2,
    UserV3,
    migrate_v1_to_v2,
    migrate_v2_to_v3,
)
from tests.utils import envelope_model, make_engine, register_models


def _latest_resolver(
    registry: Registry[types.VersionValue],
) -> types.TargetResolver:
    def resolve(kind: types.ModelKind, current: types.Versionable) -> types.Versionable:
        return registry.latest(kind)

    return resolve


def _null_resolver() -> types.TargetResolver:
    def resolve(
        kind: types.ModelKind, current: types.Versionable
    ) -> types.Versionable | None:
        return None

    return resolve


@pytest.mark.parametrize("registry", [semver.Version], indirect=True)
def test_compound_key_empty_payload_returns_no_entries(
    model_adapter: PydanticModelAdapter,
    discovery_settings: DiscoverySettings,
    registry: Registry[semver.Version],
) -> None:
    walker = CompoundKeyWalker(registry, settings=discovery_settings)
    entries = list(walker.discover({}, target_resolver=_null_resolver(), max_depth=-1))
    assert entries == []


@pytest.mark.parametrize("registry", [semver.Version], indirect=True)
@pytest.mark.parametrize(
    "walker_cls, container",
    [
        (CompoundKeyWalker, None),
        (PydanticWalker, UserContainer),
    ],
)
def test_finds_registered_versioned_dict(
    walker_cls: type[CompoundKeyWalker | PydanticWalker],
    container: type | None,
    model_adapter: PydanticModelAdapter,
    discovery_settings: DiscoverySettings,
    registry: Registry[semver.Version],
) -> None:
    register_models(model_adapter, registry, discovery_settings, UserV1, UserV2)
    payload = {
        "document": {
            "kind": "User",
            "version": "1.0.0",
            "name": "Alice",
            "email": "a@example.com",
            "role": "user",
        }
    }
    kwargs: dict[str, Any] = {
        "target_resolver": _latest_resolver(registry),
        "max_depth": -1,
    }
    if container is not None:
        kwargs["container"] = container
    entries = list(
        walker_cls(registry, settings=discovery_settings).discover(payload, **kwargs)
    )
    assert len(entries) == 1
    assert entries[0][0] == ("document",)
    assert entries[0][2].model is UserV1


@pytest.mark.parametrize("registry", [semver.Version], indirect=True)
def test_compound_key_unknown_version_is_skipped(
    model_adapter: PydanticModelAdapter,
    discovery_settings: DiscoverySettings,
    registry: Registry[semver.Version],
) -> None:
    register_models(model_adapter, registry, discovery_settings, UserV1)
    payload = {
        "document": {
            "kind": "User",
            "version": "9.9.9",
            "name": "Alice",
        }
    }
    walker = CompoundKeyWalker(registry, settings=discovery_settings)
    entries = list(walker.discover(payload, target_resolver=_latest_resolver(registry)))
    assert entries == []


@pytest.mark.parametrize("registry", [semver.Version], indirect=True)
def test_compound_key_max_depth_exceeded_for_nested_entry(
    model_adapter: PydanticModelAdapter,
    discovery_settings: DiscoverySettings,
    registry: Registry[semver.Version],
) -> None:
    register_models(model_adapter, registry, discovery_settings, UserV1)
    walker = CompoundKeyWalker(registry, settings=discovery_settings)
    payload = {
        "document": {
            "kind": "User",
            "version": "1.0.0",
            "name": "Alice",
            "nested": {
                "kind": "User",
                "version": "1.0.0",
                "name": "Bob",
            },
        }
    }
    with pytest.raises(MaxDepthExceededError):
        list(
            walker.discover(
                payload,
                target_resolver=_latest_resolver(registry),
                max_depth=0,
            )
        )


@pytest.mark.parametrize("registry", [semver.Version], indirect=True)
def test_pydantic_walker_requires_container(
    model_adapter: PydanticModelAdapter,
    discovery_settings: DiscoverySettings,
    registry: Registry[semver.Version],
) -> None:
    walker = PydanticWalker(registry, settings=discovery_settings)
    with pytest.raises(DiscoveryValidationError, match="container model"):
        list(walker.discover({}, target_resolver=_null_resolver()))


@pytest.mark.parametrize("registry", [semver.Version], indirect=True)
@pytest.mark.parametrize(
    "settings",
    [
        DiscoverySettings(validation_mode="strict"),
        DiscoverySettings(validation_mode="lax"),
    ],
)
def test_pydantic_walker_invalid_payload_raises(
    model_adapter: PydanticModelAdapter,
    discovery_settings: DiscoverySettings,
    registry: Registry[semver.Version],
    settings: DiscoverySettings,
) -> None:
    register_models(model_adapter, registry, discovery_settings, UserV1)
    walker = PydanticWalker(registry, settings=settings)
    payload = {
        "document": {
            "kind": "User",
            "version": "1.0.0",
            "name": "Alice",
            "email": "a@example.com",
            "role": "wrong-role",
        }
    }
    with pytest.raises(DiscoveryValidationError):
        list(
            walker.discover(
                payload,
                container=UserContainer,
                target_resolver=_latest_resolver(registry),
            )
        )


@pytest.mark.parametrize("registry", [semver.Version], indirect=True)
@pytest.mark.parametrize(
    "settings",
    [DiscoverySettings(validation_mode="none")],
)
def test_pydantic_walker_validation_mode_none_skips_model_validate(
    model_adapter: PydanticModelAdapter,
    discovery_settings: DiscoverySettings,
    registry: Registry[semver.Version],
    settings: DiscoverySettings,
) -> None:
    register_models(model_adapter, registry, discovery_settings, UserV1)
    walker = PydanticWalker(registry, settings=settings)
    payload = {
        "document": {
            "kind": "User",
            "version": "1.0.0",
            "name": "Alice",
            "email": "a@example.com",
            "role": "wrong-role",
        }
    }
    entries = list(
        walker.discover(
            payload,
            container=UserContainer,
            target_resolver=_latest_resolver(registry),
        )
    )
    assert len(entries) == 1


@pytest.fixture
def semver_engine(
    model_adapter: PydanticModelAdapter,
    discovery_settings: DiscoverySettings,
    semver_registry: Registry[semver.Version],
) -> Engine:
    for model in (UserV1, UserV2, UserV3):
        semver_registry.store_model(
            envelope_model(model_adapter, discovery_settings, model)
        )
    eng = make_engine(semver_registry, MigrationSettings())
    eng.store_migration(
        (
            envelope_model(model_adapter, discovery_settings, UserV1),
            envelope_model(model_adapter, discovery_settings, UserV2),
        ),
        migrate_v1_to_v2,
    )
    eng.store_migration(
        (
            envelope_model(model_adapter, discovery_settings, UserV2),
            envelope_model(model_adapter, discovery_settings, UserV3),
        ),
        migrate_v2_to_v3,
    )
    # Register backward migrations so direction="any" can converge downward.
    eng.store_migration(
        (
            envelope_model(model_adapter, discovery_settings, UserV2),
            envelope_model(model_adapter, discovery_settings, UserV1),
        ),
        lambda d: d,
    )
    eng.store_migration(
        (
            envelope_model(model_adapter, discovery_settings, UserV3),
            envelope_model(model_adapter, discovery_settings, UserV2),
        ),
        lambda d: d,
    )
    return eng


@pytest.fixture
def chrono_engine(
    model_adapter: PydanticModelAdapter,
    discovery_settings: DiscoverySettings,
    date_registry: Registry[pendulum.Date],
) -> Engine:
    for model in (UserV20250310, UserV20251231):
        date_registry.store_model(
            envelope_model(model_adapter, discovery_settings, model)
        )
    eng = make_engine(date_registry, MigrationSettings())
    eng.store_migration(
        (
            envelope_model(model_adapter, discovery_settings, UserV20250310),
            envelope_model(model_adapter, discovery_settings, UserV20251231),
        ),
        migrate_chrono_v1_to_v2,
    )
    return eng


def test_engine_migrates_to_latest(semver_engine: Engine) -> None:
    payload = {
        "document": {
            "kind": "User",
            "version": "1.0.0",
            "name": "Alice",
            "email": "a@example.com",
            "role": "user",
        }
    }
    result = semver_engine.migrate(payload)
    assert result["document"]["version"] == "3.0.0"
    assert result["document"]["age"] == 0


def test_engine_container_guided_migration(semver_engine: Engine) -> None:
    payload = {
        "document": {
            "kind": "User",
            "version": "1.0.0",
            "name": "Alice",
            "email": "a@example.com",
            "role": "user",
        }
    }
    result = semver_engine.migrate(payload, container=UserContainer)
    assert result["document"]["version"] == "3.0.0"


def test_engine_explicit_target_versionable(
    semver_engine: Engine,
    model_adapter: PydanticModelAdapter,
    discovery_settings: DiscoverySettings,
) -> None:
    target = envelope_model(model_adapter, discovery_settings, UserV2)
    payload = {
        "document": {
            "kind": "User",
            "version": "1.0.0",
            "name": "Alice",
            "email": "a@example.com",
            "role": "user",
        }
    }
    result = semver_engine.migrate(payload, target=target)
    assert result["document"]["version"] == "2.0.0"
    assert result["document"]["age"] is None


@pytest.mark.parametrize(
    "target, expected_version",
    [
        ({"User": UserV2}, "2.0.0"),
        ({"User": "skip"}, "1.0.0"),
        (None, "3.0.0"),
    ],
)
def test_engine_target_policy(
    semver_engine: Engine,
    target: dict[str, Any] | None,
    expected_version: str,
) -> None:
    payload = {
        "document": {
            "kind": "User",
            "version": "1.0.0",
            "name": "Alice",
            "email": "a@example.com",
            "role": "user",
        }
    }
    result = semver_engine.migrate(payload, target=target)
    assert result["document"]["version"] == expected_version


def test_engine_no_op_when_source_equals_target(semver_engine: Engine) -> None:
    payload = {
        "document": {
            "kind": "User",
            "version": "3.0.0",
            "name": "Alice",
            "email": "a@example.com",
            "role": "user",
            "age": 0,
            "status": "active",
        }
    }
    result = semver_engine.migrate(payload)
    assert result["document"]["version"] == "3.0.0"


def test_engine_forward_direction_policy_skip(semver_engine: Engine) -> None:
    payload = {
        "document": {
            "kind": "User",
            "version": "3.0.0",
            "name": "Alice",
            "email": "a@example.com",
            "role": "user",
            "age": 0,
            "status": "active",
        }
    }
    result = semver_engine.migrate(
        payload, target=UserV1, direction="forward", on_direction_violation="skip"
    )
    assert result["document"]["version"] == "3.0.0"


def test_engine_any_direction_policy(semver_engine: Engine) -> None:
    payload = {
        "document": {
            "kind": "User",
            "version": "3.0.0",
            "name": "Alice",
            "email": "a@example.com",
            "role": "user",
            "age": 0,
            "status": "active",
        }
    }
    result = semver_engine.migrate(payload, target=UserV1)
    assert result["document"]["version"] == "1.0.0"


def test_chrono_engine_migrates_to_latest(
    chrono_engine: Engine,
) -> None:
    payload = {
        "document": {
            "kind": "User",
            "version": "2025-03-10",
            "name": "Alice",
            "email": "a@example.com",
            "role": "user",
        }
    }
    result = chrono_engine.migrate(payload)
    assert result["document"]["version"] == "2025-12-31"
