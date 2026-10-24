"""Tests for schema-aware walkers and end-to-end Engine migration."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pendulum
import pytest
import semver

from pyverge import types
from pyverge.core import MaxDepthExceededError, PayloadValidationError
from pyverge.migration import (
    CompoundKeyWalker,
    Engine,
    JsonSchemaModelAdapter,
    PydanticModelAdapter,
    PydanticWalker,
    Registry,
    fixed_target_resolver,
    latest_target_resolver,
    skip_target_resolver,
)
from tests.examples.json import (
    USER_V1_0_0,
    USER_V2_0_0,
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
from tests.utils import envelope_model, run_engine


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            (semver.Version, "test", (), ()),
            id="pydantic_semver_empty_compound_key",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
def test_compound_key_empty_payload_returns_no_entries(
    model_adapter,
    discovery_settings,
    registry,
) -> None:
    walker = CompoundKeyWalker[semver.Version](
        registry,
        validation_mode=discovery_settings.validation_mode,
        direction=discovery_settings.direction,
        adapter=model_adapter,
    )
    entries = list(
        walker.discover(
            {}, target_resolver=skip_target_resolver(registry), max_depth=-1
        )
    )
    assert entries == []


@pytest.mark.parametrize(
    "model_adapter, registry, walker_cls, container",
    [
        pytest.param(
            PydanticModelAdapter,
            (semver.Version, "test", (UserV1, UserV2), ()),
            CompoundKeyWalker,
            None,
            id="compound_key_semver",
        ),
        pytest.param(
            PydanticModelAdapter,
            (semver.Version, "test", (UserV1, UserV2), ()),
            PydanticWalker,
            UserContainer,
            id="pydantic_container_semver",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
def test_finds_registered_versioned_dict(
    model_adapter,
    discovery_settings,
    registry,
    walker_cls: type[CompoundKeyWalker | PydanticWalker],
    container: type | None,
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
    kwargs: dict[str, Any] = {
        "target_resolver": latest_target_resolver(registry),
        "max_depth": -1,
    }
    if container is not None:
        kwargs["container"] = container
    walker_kwargs: dict[str, Any] = {
        "validation_mode": discovery_settings.validation_mode,
        "direction": discovery_settings.direction,
        "adapter": model_adapter,
    }
    entries = list(walker_cls(registry, **walker_kwargs).discover(payload, **kwargs))
    assert len(entries) == 1
    assert entries[0][0] == ("document",)
    assert entries[0][2].model is UserV1


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            (semver.Version, "test", (UserV1,), ()),
            id="pydantic_semver_user_v1_unknown",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
def test_compound_key_unknown_version_is_skipped(
    model_adapter,
    discovery_settings,
    registry,
) -> None:
    payload = {
        "document": {
            "kind": "User",
            "version": "9.9.9",
            "name": "Alice",
        }
    }
    walker = CompoundKeyWalker(
        registry,
        validation_mode=discovery_settings.validation_mode,
        direction=discovery_settings.direction,
        adapter=model_adapter,
    )
    entries = list(
        walker.discover(payload, target_resolver=latest_target_resolver(registry))
    )
    assert entries == []


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            (semver.Version, "test", (UserV1,), ()),
            id="pydantic_semver_user_v1_max_depth",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
def test_compound_key_max_depth_exceeded_for_nested_entry(
    model_adapter,
    discovery_settings,
    registry,
) -> None:
    walker = CompoundKeyWalker(
        registry,
        validation_mode=discovery_settings.validation_mode,
        direction=discovery_settings.direction,
        adapter=model_adapter,
    )
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
                target_resolver=latest_target_resolver(registry),
                max_depth=0,
            )
        )


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            (semver.Version, "test", (), ()),
            id="pydantic_semver_empty_pydantic",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
def test_walker_incompatible_container_fails_fast(
    model_adapter,
    discovery_settings,
    registry,
) -> None:
    walker = PydanticWalker(
        registry,
        validation_mode=discovery_settings.validation_mode,
        direction=discovery_settings.direction,
        adapter=model_adapter,
    )
    with pytest.raises(PayloadValidationError, match="recognized model type"):
        list(
            walker.discover(
                {}, container=dict, target_resolver=skip_target_resolver(registry)
            )
        )


def test_walker_containerless_when_none(
    model_adapter,
    discovery_settings,
    registry,
) -> None:
    walker = PydanticWalker(
        registry,
        validation_mode=discovery_settings.validation_mode,
        direction=discovery_settings.direction,
        adapter=model_adapter,
    )
    assert (
        list(walker.discover({}, target_resolver=skip_target_resolver(registry))) == []
    )


@pytest.mark.parametrize(
    "model_adapter, registry, discovery_settings",
    [
        pytest.param(
            PydanticModelAdapter,
            (semver.Version, "test", (UserV1,), ()),
            {"validation_mode": "strict"},
            id="validation_strict",
        ),
        pytest.param(
            PydanticModelAdapter,
            (semver.Version, "test", (UserV1,), ()),
            {"validation_mode": "lax"},
            id="validation_lax",
        ),
    ],
    indirect=["model_adapter", "registry", "discovery_settings"],
)
def test_pydantic_walker_invalid_payload_raises(
    model_adapter,
    discovery_settings,
    registry,
) -> None:
    walker = PydanticWalker(
        registry,
        validation_mode=discovery_settings.validation_mode,
        direction=discovery_settings.direction,
        adapter=model_adapter,
    )
    payload = {
        "document": {
            "kind": "User",
            "version": "1.0.0",
            "name": "Alice",
            "email": "a@example.com",
            "role": "wrong-role",
        }
    }
    with pytest.raises(PayloadValidationError):
        list(
            walker.discover(
                payload,
                container=UserContainer,
                target_resolver=latest_target_resolver(registry),
            )
        )


@pytest.mark.parametrize(
    "model_adapter, registry, discovery_settings",
    [
        pytest.param(
            PydanticModelAdapter,
            (semver.Version, "test", (UserV1,), ()),
            {"validation_mode": "none"},
            id="validation_none",
        ),
    ],
    indirect=["model_adapter", "registry", "discovery_settings"],
)
def test_pydantic_walker_validation_mode_none_skips_model_validate(
    model_adapter,
    discovery_settings,
    registry,
) -> None:
    walker = PydanticWalker(
        registry,
        validation_mode=discovery_settings.validation_mode,
        direction=discovery_settings.direction,
        adapter=model_adapter,
    )
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
            target_resolver=latest_target_resolver(registry),
        )
    )
    assert len(entries) == 1


@pytest.mark.parametrize(
    "model_adapter, registry, expected_version, expected_age",
    [
        pytest.param(
            PydanticModelAdapter,
            (
                semver.Version,
                "test",
                (UserV1, UserV2, UserV3),
                (
                    ((UserV1, UserV2), migrate_v1_to_v2),
                    ((UserV2, UserV3), migrate_v2_to_v3),
                ),
            ),
            "3.0.0",
            0,
            id="engine_migrate_latest",
        ),
        pytest.param(
            JsonSchemaModelAdapter,
            (
                semver.Version,
                "test",
                (USER_V1_0_0, USER_V2_0_0),
                (((USER_V1_0_0, USER_V2_0_0), lambda d, _: {**d, "version": "2.0.0"}),),
            ),
            "2.0.0",
            None,
            id="engine_migrate_latest_json_schema",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
# xfail: runtime moved out of Engine; retarget with runtime (task 7.11).
@pytest.mark.xfail(reason="runtime moved out of Engine; see task 7.11")
def test_engine_migrates_to_latest(
    engine: Engine[types.VersionValue], expected_version: str, expected_age: int | None
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
    result = run_engine(engine, payload, target=latest_target_resolver(engine.registry))
    assert result["document"]["version"] == expected_version
    assert result["document"]["age"] == expected_age


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            (
                semver.Version,
                "test",
                (UserV1, UserV2, UserV3),
                (
                    ((UserV1, UserV2), migrate_v1_to_v2),
                    ((UserV2, UserV3), migrate_v2_to_v3),
                ),
            ),
            id="engine_container_guided",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
# xfail: runtime moved out of Engine; retarget with runtime (task 7.11).
@pytest.mark.xfail(reason="runtime moved out of Engine; see task 7.11")
def test_engine_container_guided_migration(engine: Engine[types.VersionValue]) -> None:
    payload = {
        "document": {
            "kind": "User",
            "version": "1.0.0",
            "name": "Alice",
            "email": "a@example.com",
            "role": "user",
        }
    }
    result = run_engine(
        engine,
        payload,
        target=latest_target_resolver(engine.registry),
        container=UserContainer,
    )
    assert result["document"]["version"] == "3.0.0"


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            (
                semver.Version,
                "test",
                (UserV1, UserV2, UserV3),
                (
                    ((UserV1, UserV2), migrate_v1_to_v2),
                    ((UserV2, UserV3), migrate_v2_to_v3),
                ),
            ),
            id="engine_explicit_target_v2",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
# xfail: runtime moved out of Engine; retarget with runtime (task 7.11).
@pytest.mark.xfail(reason="runtime moved out of Engine; see task 7.11")
def test_engine_explicit_target_versionable(
    engine: Engine[types.VersionValue],
    model_adapter: PydanticModelAdapter,
    discovery_settings,
) -> None:
    target_model = envelope_model(model_adapter, discovery_settings, UserV2)
    target = fixed_target_resolver(engine.registry, target_model)
    payload = {
        "document": {
            "kind": "User",
            "version": "1.0.0",
            "name": "Alice",
            "email": "a@example.com",
            "role": "user",
        }
    }
    result = run_engine(engine, payload, target=target)
    assert result["document"]["version"] == "2.0.0"
    assert result["document"]["age"] is None


@pytest.mark.parametrize(
    "model_adapter, registry, resolver_factory, expected_version",
    [
        pytest.param(
            PydanticModelAdapter,
            (
                semver.Version,
                "test",
                (UserV1, UserV2, UserV3),
                (
                    ((UserV1, UserV2), migrate_v1_to_v2),
                    ((UserV2, UserV3), migrate_v2_to_v3),
                ),
            ),
            latest_target_resolver,
            "3.0.0",
            id="latest",
        ),
        pytest.param(
            PydanticModelAdapter,
            (
                semver.Version,
                "test",
                (UserV1, UserV2, UserV3),
                (
                    ((UserV1, UserV2), migrate_v1_to_v2),
                    ((UserV2, UserV3), migrate_v2_to_v3),
                ),
            ),
            skip_target_resolver,
            "1.0.0",
            id="skip",
        ),
        pytest.param(
            PydanticModelAdapter,
            (
                semver.Version,
                "test",
                (UserV1, UserV2, UserV3),
                (
                    ((UserV1, UserV2), migrate_v1_to_v2),
                    ((UserV2, UserV3), migrate_v2_to_v3),
                ),
            ),
            latest_target_resolver,
            "3.0.0",
            id="default-latest",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
# xfail: runtime moved out of Engine; retarget with runtime (task 7.11).
@pytest.mark.xfail(reason="runtime moved out of Engine; see task 7.11")
def test_engine_target_policy(
    engine: Engine[types.VersionValue],
    resolver_factory: Callable[[Registry[semver.Version]], Any],
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
    resolver = resolver_factory(engine.registry)  # ty: ignore[invalid-argument-type]
    result = run_engine(engine, payload, target=resolver)
    assert result["document"]["version"] == expected_version


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            (
                semver.Version,
                "test",
                (UserV1, UserV2, UserV3),
                (
                    ((UserV1, UserV2), migrate_v1_to_v2),
                    ((UserV2, UserV3), migrate_v2_to_v3),
                ),
            ),
            id="engine_noop_same_version",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
# xfail: runtime moved out of Engine; retarget with runtime (task 7.11).
@pytest.mark.xfail(reason="runtime moved out of Engine; see task 7.11")
def test_engine_no_op_when_source_equals_target(
    engine: Engine[types.VersionValue],
) -> None:
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
    result = run_engine(engine, payload, target=latest_target_resolver(engine.registry))
    assert result["document"]["version"] == "3.0.0"


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            (
                semver.Version,
                "test",
                (UserV1, UserV2, UserV3),
                (
                    ((UserV1, UserV2), migrate_v1_to_v2),
                    ((UserV2, UserV3), migrate_v2_to_v3),
                ),
            ),
            id="engine_forward_skip",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
# xfail: runtime moved out of Engine; retarget with runtime (task 7.11).
@pytest.mark.xfail(reason="runtime moved out of Engine; see task 7.11")
def test_engine_forward_direction_policy_skip(
    engine: Engine[types.VersionValue],
    model_adapter: PydanticModelAdapter,
    discovery_settings,
) -> None:
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
    target = fixed_target_resolver(
        engine.registry,
        envelope_model(model_adapter, discovery_settings, UserV1),
    )
    result = run_engine(
        engine,
        payload,
        target=target,
        direction="forward",
        on_direction_violation="skip",
    )
    assert result["document"]["version"] == "3.0.0"


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            (
                semver.Version,
                "test",
                (UserV1, UserV2, UserV3),
                (
                    ((UserV1, UserV2), migrate_v1_to_v2),
                    ((UserV2, UserV3), migrate_v2_to_v3),
                    ((UserV2, UserV1), lambda data, _: data, True),
                    ((UserV3, UserV2), lambda data, _: data, True),
                ),
            ),
            id="engine_any_direction_backward",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
# xfail: runtime moved out of Engine; retarget with runtime (task 7.11).
@pytest.mark.xfail(reason="runtime moved out of Engine; see task 7.11")
def test_engine_any_direction_policy(
    engine: Engine[types.VersionValue],
    model_adapter: PydanticModelAdapter,
    discovery_settings,
) -> None:
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
    target = fixed_target_resolver(
        engine.registry,
        envelope_model(model_adapter, discovery_settings, UserV1),
    )
    result = run_engine(
        engine,
        payload,
        target=target,
    )
    assert result["document"]["version"] == "1.0.0"


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            (
                pendulum.Date,
                "test",
                (UserV20250310, UserV20251231),
                (((UserV20250310, UserV20251231), migrate_chrono_v1_to_v2),),
            ),
            id="pydantic_chrono_engine",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
# xfail: runtime moved out of Engine; retarget with runtime (task 7.11).
@pytest.mark.xfail(reason="runtime moved out of Engine; see task 7.11")
def test_chrono_engine_migrates_to_latest(
    engine: Engine[types.VersionValue],
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
    result = run_engine(engine, payload, target=latest_target_resolver(engine.registry))
    assert result["document"]["version"] == "2025-12-31"
