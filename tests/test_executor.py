from __future__ import annotations

import functools
from collections.abc import Callable
from dataclasses import replace

import pytest
import semver
from pydantic import BaseModel

from pyverge import types
from pyverge.core import (
    DiscoveryValidationError,
    MigrationError,
    MigrationNotFoundError,
    RegistryError,
    VersionNode,
)
from pyverge.migration import (
    Engine,
    JsonPatchMigration,
    LevelParallelExecutor,
    PydanticModelAdapter,
    Registry,
    SequentialExecutor,
    StepExecutor,
    earliest_target_resolver,
    fixed_target_resolver,
    latest_target_resolver,
    multi_target_resolver,
    skip_target_resolver,
)
from pyverge.providers.types import (
    ModelHandle,
)
from tests.examples.pydantic.semver_nested import (
    AddressV1,
    AddressV2,
    AddressV3,
    ContactV1,
    ContactV2,
    PersonV1,
    PersonV2,
    demote_address,
    migrate_address_100_200,
    migrate_contact_100_200,
    preserve_children_person,
    promote_address,
)
from tests.utils import edge_from_models, envelope_model


@pytest.mark.parametrize(
    "executor",
    [
        pytest.param(SequentialExecutor(), id="sequential"),
        pytest.param(LevelParallelExecutor(), id="level_parallel"),
    ],
)
@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            [
                semver.Version,
                "test",
                [PersonV1, PersonV2, AddressV1, AddressV2, ContactV1, ContactV2],
                [
                    ((PersonV1, PersonV2), preserve_children_person),
                    ((AddressV1, AddressV2), migrate_address_100_200),
                    ((ContactV1, ContactV2), migrate_contact_100_200),
                ],
            ],
            id="pydantic_nested",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
def test_executor_returns_new_payload(
    engine: Engine[types.VersionValue],
    executor: types.Executor,
    snapshot,
) -> None:
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

    result = engine.migrate(
        payload,
        target=latest_target_resolver(engine.registry),
        executor=executor,
    )

    # Original payload is untouched
    assert payload["document"]["version"] == "1.0.0"
    assert "email" not in payload["document"]

    # Migrated copy has latest versions and added defaults.
    # The parent Person migration preserves already-migrated contacts.
    assert result == snapshot


@pytest.mark.parametrize(
    "executor",
    [
        pytest.param(SequentialExecutor(), id="sequential"),
        pytest.param(LevelParallelExecutor(), id="level_parallel"),
    ],
)
@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            [
                semver.Version,
                "test",
                [PersonV1, PersonV2, AddressV1, AddressV2, ContactV1, ContactV2],
                [
                    ((PersonV1, PersonV2), preserve_children_person),
                    ((AddressV1, AddressV2), migrate_address_100_200),
                    ((ContactV1, ContactV2), migrate_contact_100_200),
                ],
            ],
            id="pydantic_nested",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
def test_executor_noop_when_source_is_target(
    engine: Engine[types.VersionValue],
    executor: types.Executor,
    snapshot,
) -> None:
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

    result = engine.migrate(
        payload,
        target=latest_target_resolver(engine.registry),
        executor=executor,
    )

    assert result == snapshot


class TestStepExecutor:
    """StepExecutor resolves and runs a single migration edge."""

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [PersonV1, PersonV2], []],
                [PersonV1, PersonV2],
                id="pydantic_person_v1_v2",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_execute_step_runs_registered_migration_and_updates_version(
        self,
        engine: Engine[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        edge = edge_from_models(
            engine.adapter,
            engine.settings,
            *models,
            func=lambda d: {"version": "2.0.0", "name": d.get("name")},
        )
        engine.registry.store_migration(edge)

        source, target = [
            envelope_model(engine.adapter, engine.settings, model) for model in models
        ]

        step_executor = StepExecutor(engine.registry)
        result = step_executor.execute_step(
            source, target, {"version": "1.0.0", "name": "Alice"}, (), "version"
        )

        assert result == {"version": "2.0.0", "name": "Alice"}

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [PersonV1, PersonV2], []],
                [PersonV1, PersonV2],
                id="pydantic_person_v1_v2",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_execute_step_raises_when_migration_missing(
        self,
        engine: Engine[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        source, target = [
            envelope_model(engine.adapter, engine.settings, model) for model in models
        ]

        step_executor = StepExecutor(engine.registry)
        with pytest.raises(MigrationNotFoundError):
            step_executor.execute_step(
                source, target, {"version": "1.0.0"}, (), "version"
            )


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            [semver.Version, "test", [PersonV1, PersonV2, AddressV1, AddressV2], []],
            id="pydantic_person_address",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
def test_sequential_executor_runs_in_topological_order(
    engine: Engine[types.VersionValue],
) -> None:
    order: list[str] = []

    def _track_person(data: dict) -> dict:
        order.append("person")
        return preserve_children_person(data)

    def _track_address(data: dict) -> dict:
        order.append("address")
        return migrate_address_100_200(data)

    engine.store_migration(
        (
            envelope_model(engine.adapter, engine.settings, PersonV1),
            envelope_model(engine.adapter, engine.settings, PersonV2),
        ),
        _track_person,
    )
    engine.store_migration(
        (
            envelope_model(engine.adapter, engine.settings, AddressV1),
            envelope_model(engine.adapter, engine.settings, AddressV2),
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

    engine.migrate(payload, target=latest_target_resolver(engine.registry))

    # Address is nested inside Person, so it must run before Person.
    assert order == ["address", "person"]


@pytest.mark.parametrize(
    "func_factory",
    [
        pytest.param(
            lambda: lambda data: (_ for _ in ()).throw(RuntimeError("boom")),
            id="python-callable",
        ),
        pytest.param(
            lambda: (
                JsonPatchMigration(
                    {
                        "from": "1.0.0",
                        "to": "2.0.0",
                        "ops": [{"op": "test", "path": "/type", "value": "X"}],
                    }
                ).patch
            ),
            id="jsonpatch-spec",
        ),
    ],
)
@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            [semver.Version, "test", [PersonV1, PersonV2], []],
            id="pydantic_person_v1_v2",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
def test_executor_propagates_migration_error(
    engine: Engine[types.VersionValue],
    func_factory: Callable,
) -> None:
    engine.store_migration(
        (
            envelope_model(engine.adapter, engine.settings, PersonV1),
            envelope_model(engine.adapter, engine.settings, PersonV2),
        ),
        func_factory(),
    )

    payload = {
        "document": {
            "kind": "Person",
            "version": "1.0.0",
            "name": "Alice",
        }
    }

    with pytest.raises(MigrationError, match="Migration failed"):
        engine.migrate(payload, target=latest_target_resolver(engine.registry))


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            [
                semver.Version,
                "test",
                [PersonV1, PersonV2, AddressV1, AddressV2, ContactV1, ContactV2],
                [
                    ((PersonV1, PersonV2), preserve_children_person),
                    ((AddressV1, AddressV2), migrate_address_100_200),
                    ((ContactV1, ContactV2), migrate_contact_100_200),
                ],
            ],
            id="pydantic_nested",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
def test_level_parallel_executor_single_entry_uses_no_pool(
    engine: Engine[types.VersionValue],
    snapshot,
) -> None:
    """A graph with one entry per level should not require thread workers."""
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

    result = engine.migrate(
        payload,
        target=latest_target_resolver(engine.registry),
        executor=LevelParallelExecutor(max_workers=2),
    )
    assert result == snapshot


@pytest.mark.parametrize(
    "model_adapter, registry, payload, resolver_factory, expected_error",
    [
        pytest.param(
            PydanticModelAdapter,
            [
                semver.Version,
                "test",
                [PersonV1, PersonV2, AddressV1, AddressV3],
                [
                    ((PersonV1, PersonV2), preserve_children_person),
                    ((AddressV1, AddressV3), promote_address),
                    ((AddressV3, AddressV1), demote_address),
                ],
            ],
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
            latest_target_resolver,
            None,
            id="latest",
        ),
        pytest.param(
            PydanticModelAdapter,
            [
                semver.Version,
                "test",
                [PersonV1, PersonV2, AddressV1, AddressV3],
                [
                    ((PersonV1, PersonV2), preserve_children_person),
                    ((AddressV1, AddressV3), promote_address),
                    ((AddressV3, AddressV1), demote_address),
                ],
            ],
            {
                "document": {
                    "kind": "Address",
                    "version": "3.0.0",
                    "street": "Main",
                    "city": "Paris",
                    "country": None,
                    "postal_code": None,
                    "region": "IDF",
                }
            },
            earliest_target_resolver,
            None,
            id="earliest",
        ),
        pytest.param(
            PydanticModelAdapter,
            [
                semver.Version,
                "test",
                [PersonV1, PersonV2, AddressV1, AddressV3],
                [
                    ((PersonV1, PersonV2), preserve_children_person),
                    ((AddressV1, AddressV3), promote_address),
                    ((AddressV3, AddressV1), demote_address),
                ],
            ],
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
            skip_target_resolver,
            None,
            id="skip",
        ),
        pytest.param(
            PydanticModelAdapter,
            [
                semver.Version,
                "test",
                [PersonV1, PersonV2, AddressV1, AddressV3],
                [
                    ((PersonV1, PersonV2), preserve_children_person),
                    ((AddressV1, AddressV3), promote_address),
                    ((AddressV3, AddressV1), demote_address),
                ],
            ],
            {
                "document": {
                    "kind": "Person",
                    "version": "1.0.0",
                    "name": "Alice",
                    "address": {"version": "1.0.0", "street": "Main", "city": "Paris"},
                }
            },
            functools.partial(
                fixed_target_resolver,
                target=VersionNode(
                    _model=PersonV2,
                    _value=semver.Version(2, 0, 0),
                    _kind="Person",
                ),
            ),
            None,
            id="fixed",
        ),
        pytest.param(
            PydanticModelAdapter,
            [
                semver.Version,
                "test",
                [PersonV1, PersonV2, AddressV1, AddressV3],
                [
                    ((PersonV1, PersonV2), preserve_children_person),
                    ((AddressV1, AddressV3), promote_address),
                    ((AddressV3, AddressV1), demote_address),
                ],
            ],
            {
                "document": {
                    "kind": "Person",
                    "version": "1.0.0",
                    "name": "Alice",
                    "address": {
                        "kind": "Address",
                        "version": "3.0.0",
                        "street": "Main",
                        "city": "Paris",
                        "country": None,
                        "postal_code": None,
                        "region": "IDF",
                    },
                }
            },
            lambda registry: multi_target_resolver(
                {
                    "Person": latest_target_resolver(registry),
                    "*": earliest_target_resolver(registry),
                }
            ),
            None,
            id="multi_wildcard_fallback",
        ),
        pytest.param(
            PydanticModelAdapter,
            [
                semver.Version,
                "test",
                [PersonV1, PersonV2, AddressV1, AddressV3],
                [
                    ((PersonV1, PersonV2), preserve_children_person),
                    ((AddressV1, AddressV3), promote_address),
                    ((AddressV3, AddressV1), demote_address),
                ],
            ],
            {
                "document": {
                    "kind": "Address",
                    "version": "1.0.0",
                    "street": "Main",
                    "city": "Paris",
                }
            },
            functools.partial(
                fixed_target_resolver,
                target=VersionNode(
                    _model=PersonV2,
                    _value=semver.Version(2, 0, 0),
                    _kind="Person",
                ),
            ),
            RegistryError,
            id="fixed_wrong_kind_raises",
        ),
        pytest.param(
            PydanticModelAdapter,
            [
                semver.Version,
                "test",
                [PersonV1, PersonV2, AddressV1, AddressV3],
                [
                    ((PersonV1, PersonV2), preserve_children_person),
                    ((AddressV1, AddressV3), promote_address),
                    ((AddressV3, AddressV1), demote_address),
                ],
            ],
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
            functools.partial(
                fixed_target_resolver,
                target=VersionNode(
                    _model=PersonV2,
                    _value=semver.Version(9, 9, 9),
                    _kind="Person",
                ),
            ),
            RegistryError,
            id="fixed_unregistered_target_raises",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
def test_target_resolver_converges_end_to_end(
    engine: Engine[types.VersionValue],
    payload: dict,
    resolver_factory: Callable[[Registry[types.VersionValue]], types.TargetResolver],
    expected_error: type[Exception] | None,
    snapshot,
) -> None:
    """Every resolver policy drives ``engine.migrate`` to its target version."""
    if expected_error is not None:
        with pytest.raises(expected_error):
            engine.migrate(payload, target=resolver_factory(engine.registry))
        return

    result = engine.migrate(payload, target=resolver_factory(engine.registry))

    assert result == snapshot


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            [semver.Version, "test", [PersonV1, PersonV2], []],
            id="pydantic_person_v1_v2",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
def test_executor_gate_rejects_field_shallow_container(
    engine: Engine[types.VersionValue],
) -> None:
    """The executor fails fast when the plan's container cannot cover fields.

    A container that the adapter recognizes but that omits the target's fields
    must raise before any migration executes — the gate lives in the executor.
    """
    engine.store_migration(
        (
            envelope_model(engine.adapter, engine.settings, PersonV1),
            envelope_model(engine.adapter, engine.settings, PersonV2),
        ),
        preserve_children_person,
    )

    payload = {"document": {"kind": "Person", "version": "1.0.0", "name": "Alice"}}
    plan = engine.graph_builder.build(
        payload,
        target_resolver=latest_target_resolver(engine.registry),
    )
    # Force a container that recognizes the type but declares no fields.
    shallow = replace(plan, container=type("Empty", (BaseModel,), {}))
    with pytest.raises(DiscoveryValidationError, match="incompatible"):
        engine.default_executor.run(
            shallow,
            registry=engine.registry,
            entry_migration=engine.entry_migration,
            adapter=engine.adapter,
            version_property=engine.settings.version_property,
            direction=engine.settings.direction,
            on_direction_violation=engine.settings.on_direction_violation,
            on_missing_path=engine.settings.on_missing_path,
        )
