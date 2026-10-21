from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable
from dataclasses import replace
from unittest.mock import MagicMock

import pytest
import semver
from pydantic import BaseModel

from pyverge import types
from pyverge.core import (
    DiscoveryValidationError,
    MigrationError,
    MigrationNotFoundError,
    MigrationSettings,
    RegistryError,
    VersionNode,
)
from pyverge.core.types import ModelData
from pyverge.executor import StepRequest
from pyverge.migration import (
    AsyncLevelParallelExecutor,
    AsyncSequentialExecutor,
    DefaultEntryPlanner,
    Engine,
    ExecutionPolicy,
    GraphEntry,
    JsonPatchMigration,
    LevelParallelExecutor,
    LocalExecutionBackend,
    MigrationContext,
    MigrationGraph,
    MigrationPlan,
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
from tests.utils import edge_from_models, envelope_model, run_engine


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

    result = run_engine(
        engine,
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

    result = run_engine(
        engine,
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
            func=lambda d, _: {"version": "2.0.0", "name": d.get("name")},
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
    def test_execute_step_passes_context_to_provider(
        self,
        engine: Engine[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        seen: list[MigrationContext] = []

        def _migrate(data: dict, context: MigrationContext | None = None) -> dict:
            assert context is not None
            seen.append(context)
            return {
                "version": "2.0.0",
                "name": data["name"],
                "tenant_id": context["tenant_id"],
            }

        source, target = [
            envelope_model(engine.adapter, engine.settings, model) for model in models
        ]
        engine.store_migration((source, target), _migrate)
        context = MigrationContext.create({"tenant_id": "tenant_99"})

        result = StepExecutor(engine.registry).execute_step(
            source,
            target,
            {"version": "1.0.0", "name": "Alice"},
            (),
            "version",
            context,
        )

        assert result == {
            "version": "2.0.0",
            "name": "Alice",
            "tenant_id": "tenant_99",
        }
        assert seen == [context]

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

    def _track_person(data: dict, context: MigrationContext | None = None) -> dict:
        order.append("person")
        return preserve_children_person(data)

    def _track_address(data: dict, context: MigrationContext | None = None) -> dict:
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

    run_engine(engine, payload, target=latest_target_resolver(engine.registry))

    # Address is nested inside Person, so it must run before Person.
    assert order == ["address", "person"]


@pytest.mark.parametrize(
    "func_factory",
    [
        pytest.param(
            lambda: lambda data, _: (_ for _ in ()).throw(RuntimeError("boom")),
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
        run_engine(engine, payload, target=latest_target_resolver(engine.registry))


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

    result = run_engine(
        engine,
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
    """Every resolver policy drives ``engine.prepare`` to its target version."""
    if expected_error is not None:
        with pytest.raises(expected_error):
            run_engine(engine, payload, target=resolver_factory(engine.registry))
        return

    result = run_engine(engine, payload, target=resolver_factory(engine.registry))

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
        SequentialExecutor().run(
            shallow,
            registry=engine.registry,
            entry_migration=engine.entry_migration,
            adapter=engine.adapter,
            version_property=engine.settings.version_property,
            direction=engine.settings.direction,
            on_direction_violation=engine.settings.on_direction_violation,
            on_missing_path=engine.settings.on_missing_path,
        )


class TestExecutionPolicy:
    @pytest.mark.parametrize(
        "settings, expected",
        [
            pytest.param(MigrationSettings(), SequentialExecutor, id="sync-sequential"),
            pytest.param(
                MigrationSettings(parallel_workers=2),
                LevelParallelExecutor,
                id="sync-parallel",
            ),
            pytest.param(
                MigrationSettings(execution_mode="async"),
                AsyncSequentialExecutor,
                id="async-sequential",
            ),
            pytest.param(
                MigrationSettings(execution_mode="async", parallel_workers=2),
                AsyncLevelParallelExecutor,
                id="async-parallel",
            ),
        ],
    )
    def test_builds_executor_from_settings(
        self, settings: MigrationSettings, expected: type
    ) -> None:
        assert isinstance(ExecutionPolicy(settings).build(), expected)


class TestLocalExecutionBackend:
    def test_run_entry_delegates_to_entry_planner(self) -> None:
        task = MagicMock()
        task.run.return_value = {"name": "Bob"}
        entry_migration = MagicMock()
        entry_migration.migrate.return_value = task
        adapter = MagicMock()
        entry = MagicMock()
        context = MigrationContext.empty()

        backend = LocalExecutionBackend(
            registry=MagicMock(),
            entry_migration=entry_migration,
            adapter=adapter,
            version_property="version",
            direction="any",
            on_direction_violation="raise",
            on_missing_path="raise",
        )

        result = backend.run_entry(entry, {"name": "Alice"}, context)

        assert result == {"name": "Bob"}
        entry_migration.migrate.assert_called_once()
        task.run.assert_called_once_with()

    def test_ensure_compatible_delegates_to_adapter(self) -> None:
        adapter = MagicMock()
        backend = LocalExecutionBackend(
            registry=MagicMock(),
            entry_migration=DefaultEntryPlanner(),
            adapter=adapter,
            version_property="version",
            direction="any",
            on_direction_violation="raise",
            on_missing_path="raise",
        )
        plan = MagicMock()

        backend.ensure_compatible(plan)

        adapter.ensure_compatible.assert_called_once_with(
            plan.container, fields=plan.target_fields
        )

    def test_arun_entry_delegates_to_async_planner(self) -> None:
        class _Task:
            async def arun(self) -> dict:
                return {"name": "Bob"}

        class _Entry:
            def __init__(self) -> None:
                self.calls = 0

            def amigrate(self, *args: object, **kwargs: object) -> _Task:
                self.calls += 1
                return _Task()

        entry_migration = _Entry()
        backend = LocalExecutionBackend(
            registry=MagicMock(),
            entry_migration=entry_migration,
            adapter=MagicMock(),
            version_property="version",
            direction="any",
            on_direction_violation="raise",
            on_missing_path="raise",
        )

        result = asyncio.run(backend.arun_entry(MagicMock(), {"name": "Alice"}))

        assert result == {"name": "Bob"}
        assert entry_migration.calls == 1


class _RecordingBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[str | int, ...]] = []

    def ensure_compatible(self, plan: object) -> None:
        pass

    def run_entry(
        self,
        entry: GraphEntry,
        current: ModelData,
        context: MigrationContext | None,
    ) -> ModelData:
        self.calls.append(entry.path)
        return {"value": 2}

    async def arun_entry(
        self,
        entry: GraphEntry,
        current: ModelData,
        context: MigrationContext | None,
    ) -> ModelData:
        self.calls.append(entry.path)
        return {"value": 2}


def _plan(*paths: tuple[str, ...]) -> MigrationPlan:
    entries = [
        GraphEntry(path=path, source=MagicMock(), target=MagicMock())
        for path in paths
    ]
    return MigrationPlan(
        data={p[0]: {"value": 1} for p in paths},
        graph=MigrationGraph(entries),
    )


class TestStrategiesUseBackend:
    def test_sequential_execute_uses_backend(self) -> None:
        backend = _RecordingBackend()
        result = SequentialExecutor().execute(
            _plan(("a",), ("b",)), backend  # ty: ignore[invalid-argument-type]
        )

        assert result == {"a": {"value": 2}, "b": {"value": 2}}
        assert backend.calls == [("a",), ("b",)]

    def test_parallel_execute_uses_backend(self) -> None:
        backend = _RecordingBackend()
        result = LevelParallelExecutor(max_workers=2).execute(
            _plan(("a",), ("b",)), backend  # ty: ignore[invalid-argument-type]
        )

        assert result == {"a": {"value": 2}, "b": {"value": 2}}
        assert set(backend.calls) == {("a",), ("b",)}

    def test_async_sequential_execute_uses_backend(self) -> None:
        backend = _RecordingBackend()
        result = asyncio.run(
            AsyncSequentialExecutor().aexecute(
                _plan(("a",), ("b",)), backend  # ty: ignore[invalid-argument-type]
            )
        )

        assert result == {"a": {"value": 2}, "b": {"value": 2}}
        assert backend.calls == [("a",), ("b",)]

    def test_async_parallel_execute_uses_backend(self) -> None:
        backend = _RecordingBackend()
        result = asyncio.run(
            AsyncLevelParallelExecutor(max_workers=2).aexecute(
                _plan(("a",), ("b",)), backend  # ty: ignore[invalid-argument-type]
            )
        )

        assert result == {"a": {"value": 2}, "b": {"value": 2}}
        assert set(backend.calls) == {("a",), ("b",)}


class TestRemoteContract:
    def test_step_request_is_a_serializable_value(self) -> None:
        request = StepRequest(
            kind="User",
            from_version="1.0.0",
            to_version="2.0.0",
            payload={"kind": "User", "version": "1.0.0"},
            context={"tenant": "t"},
        )

        assert request.kind == "User"
        assert request.from_version == "1.0.0"
        assert request.to_version == "2.0.0"
        assert request.payload == {"kind": "User", "version": "1.0.0"}
        assert request.context == {"tenant": "t"}
