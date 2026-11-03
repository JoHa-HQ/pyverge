# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import replace
from typing import Any, cast

import pytest

from pyverge import Manager
from pyverge.core.engine import Engine
from pyverge.core.graph import (
    AnyDirection,
    GraphBuilder,
    PathFinder,
    PolicyEngine,
    TargetCompiler,
    direction_policy,
)
from pyverge.core.ids import UuidIdFactory
from pyverge.core.registry import (
    DEFAULT_HEALTH_LINTERS,
    CompatibilityLinter,
    Registry,
)
from pyverge.core.types import (
    VersionValue,
)
from pyverge.core.versioning import default_content_hasher
from pyverge.discovery.reflection import (
    CompositeDiffDiscovery,
    Reflection,
    Reflector,
)
from pyverge.migrations.backend import MigrationMaterializer
from pyverge.migrations.json_patch.backend import JsonPatchMigrationBackend
from pyverge.runtime import (
    ExecutionCoordinator,
    ExecutionPlanner,
    PayloadWalker,
    Runner,
)
from pyverge.runtime.backends import ThreadedBackend
from pyverge.runtime.clock import SystemClock
from pyverge.runtime.context import ExecutionEnvironment
from pyverge.runtime.factory import RunnerFactory
from pyverge.runtime.migrations import MigrationBindings
from pyverge.runtime.types import BackendPort
from pyverge.schemas import JsonSchemaModelAdapter, PydanticModelAdapter
from pyverge.schemas.codec import ModelCodec
from pyverge.schemas.types import (
    ModelAdapter,
)
from pyverge.settings import (
    DiscoverySettings,
    MigrationSettings,
    VersioningSettings,
    manager_kwargs,
    overrides,
    without_identity,
)
from pyverge.types import VersionEdge
from tests.utils import edge_from_nodes, envelope_model, register_models
from tests.utils.engine import register_migrations

# Example model modules are imported by tests, not collected as tests.  With
# ``--doctest-modules`` their basenames (e.g. ``semver.py``) collide with
# installed packages, so exclude them from collection.
collect_ignore_glob = ["examples/**"]


@pytest.fixture
def versioning_settings(request: pytest.FixtureRequest) -> VersioningSettings:
    custom = cast(dict, getattr(request, "param", {}))
    return VersioningSettings(**overrides(custom))


@pytest.fixture
def migration_settings(request: pytest.FixtureRequest) -> MigrationSettings:
    custom = cast(dict, getattr(request, "param", {}))
    return MigrationSettings(**without_identity(custom))


@pytest.fixture
def discovery_settings(request: pytest.FixtureRequest) -> DiscoverySettings:
    custom = cast(dict, getattr(request, "param", {}))
    return DiscoverySettings(**overrides(custom))


@pytest.fixture
def pydantic_model_adapter(
    versioning_settings: VersioningSettings,
) -> PydanticModelAdapter:
    return PydanticModelAdapter(
        codec=ModelCodec(
            namespace="test",
            version_property=versioning_settings.version_property,
            kind_property=versioning_settings.kind_property,
        )
    )


@pytest.fixture
def json_model_adapter(
    versioning_settings: VersioningSettings,
) -> JsonSchemaModelAdapter:
    return JsonSchemaModelAdapter(
        codec=ModelCodec(
            namespace="test",
            version_property=versioning_settings.version_property,
            kind_property=versioning_settings.kind_property,
        )
    )


@pytest.fixture(params=[PydanticModelAdapter])
def model_adapter(
    request: pytest.FixtureRequest,
) -> PydanticModelAdapter | JsonSchemaModelAdapter:
    provider = request.param
    if provider is JsonSchemaModelAdapter:
        return request.getfixturevalue("json_model_adapter")
    if provider is PydanticModelAdapter:
        return request.getfixturevalue("pydantic_model_adapter")
    raise ValueError(f"Unknown provider: {provider}")


@pytest.fixture(params=["test"])
def codec(
    request: pytest.FixtureRequest,
    versioning_settings: VersioningSettings,
) -> ModelCodec:
    return ModelCodec(
        namespace=request.param,
        version_property=versioning_settings.version_property,
        kind_property=versioning_settings.kind_property,
    )


@pytest.fixture
def node(
    request: pytest.FixtureRequest,
    codec: ModelCodec,
    versioning_settings: VersioningSettings,
) -> Any:
    adapter_cls, model = request.param
    adapter = adapter_cls(codec=codec)
    result = envelope_model(adapter, versioning_settings, model)
    return result


@pytest.fixture
def edge(
    request: pytest.FixtureRequest,
    codec: ModelCodec,
    versioning_settings: VersioningSettings,
) -> VersionEdge:
    adapter_cls, source_model, target_model, func = request.param
    adapter = adapter_cls(codec)
    source = envelope_model(adapter, versioning_settings, source_model)
    target = envelope_model(adapter, versioning_settings, target_model)
    return edge_from_nodes(adapter, source, target, func=func)


@pytest.fixture(scope="function", params=[(VersionValue, "test", [], [])])
def registry(
    request: pytest.FixtureRequest,
    model_adapter: PydanticModelAdapter,
    migration_settings: MigrationSettings,
    reflector: Reflector[VersionValue],
) -> Registry[VersionValue]:
    _strategy, _name, models, migrations, *rest = request.param
    namespace = rest[0] if rest else model_adapter.model_codec.namespace
    if namespace and model_adapter.model_codec.namespace != namespace:
        model_adapter.model_codec = replace(
            model_adapter.model_codec, namespace=namespace
        )
    registry = Registry[VersionValue](
        namespace=namespace,
        hasher=default_content_hasher(),
        reflection=reflector,
        linters=(
            *DEFAULT_HEALTH_LINTERS,
            CompatibilityLinter(
                frozenset(
                    {
                        model_adapter.kind_property,
                        model_adapter.version_property,
                    }
                )
            ),
        ),
        on_missing=migration_settings.on_missing,
    )
    bindings = MigrationBindings[VersionValue](name=namespace)
    if models:
        register_models(model_adapter, registry, migration_settings, *models)
    if migrations:
        register_migrations(model_adapter, registry, *migrations, bindings=bindings)
    setattr(registry, "bindings", bindings)
    return registry


@pytest.fixture
def walker(
    registry: Registry[VersionValue],
    migration_settings: MigrationSettings,
    model_adapter: PydanticModelAdapter,
) -> PayloadWalker:
    """A preconfigured :class:`PayloadWalker` bound to the shared registry.

    Pass it to ``Manager[VersionValue].configure(settings, adapter, walker=...)``
    to drive container-guided discovery.
    """
    return PayloadWalker(
        GraphBuilder().build(registry),
        adapter=model_adapter,
        validation_mode=migration_settings.validation_mode,
    )


@pytest.fixture(
    params=[(SystemClock, UuidIdFactory)],
    ids=["system-uuid"],
)
def execution_environment(
    request: pytest.FixtureRequest,
) -> ExecutionEnvironment:
    clock_cls, id_cls = request.param
    return ExecutionEnvironment(
        clock=clock_cls(),
        id_factory=id_cls(),
        logger=None,
        tracer=None,
    )


@pytest.fixture(params=[("raise", "raise", -1, "raise")])
def coordinator(
    request: pytest.FixtureRequest,
    walker: PayloadWalker[VersionValue],
    registry: Registry[VersionValue],
    model_adapter: ModelAdapter,
) -> ExecutionCoordinator[VersionValue]:
    on_direction_violation, on_missing_path, depth_limit, on_depth_violation = (
        request.param
    )
    graph = GraphBuilder().build(registry)
    return ExecutionCoordinator(
        extractor=walker,
        finder=PathFinder(
            graph=graph,
            targets=TargetCompiler(graph, model_adapter),
            policy=PolicyEngine(
                direction=AnyDirection(),
                on_direction_violation=on_direction_violation,
                on_missing_path=on_missing_path,
                depth_limit=depth_limit,
                on_depth_violation=on_depth_violation,
            ),
        ),
        planner=ExecutionPlanner(
            bindings=getattr(
                registry, "bindings", MigrationBindings(name=registry.namespace)
            )
        ),
    )


@pytest.fixture
def runner_factory(
    engine: Engine[VersionValue],
    registry: Registry[VersionValue],
    runtime_backend: BackendPort,
    runtime_environment: ExecutionEnvironment,
    migration_settings: MigrationSettings,
) -> Callable[..., Runner[VersionValue]]:
    def build(
        *,
        telemetry: tuple[Any, ...] = (),
        plan_cache_size: int = 0,
    ) -> Runner[VersionValue]:
        bindings = getattr(
            registry, "bindings", MigrationBindings(name=registry.namespace)
        )
        return RunnerFactory().create(
            engine.snapshot(),
            bindings,
            engine.adapter,
            backend=runtime_backend,
            environment=runtime_environment,
            direction=direction_policy(migration_settings.direction),
            on_direction_violation=migration_settings.on_direction_violation,
            on_missing_path=migration_settings.on_missing_path,
            depth_limit=migration_settings.max_migration_depth,
            on_depth_violation="raise",
            validation_mode=migration_settings.validation_mode,
            middleware=(),
            telemetry=telemetry,
            plan_cache_size=plan_cache_size,
        )

    return build


@pytest.fixture
def runtime_backend(
    request: pytest.FixtureRequest,
) -> Iterator[BackendPort]:
    backend_cls, kwargs = getattr(
        request, "param", (ThreadedBackend, {"max_workers": 0})
    )
    backend = backend_cls(**kwargs)
    yield backend
    close = getattr(backend, "close", None)
    if close is not None:
        close()


@pytest.fixture
def runtime_environment() -> ExecutionEnvironment:
    return ExecutionEnvironment(
        clock=SystemClock(),
        id_factory=UuidIdFactory(),
        logger=None,
        tracer=None,
    )


@pytest.fixture
def runner(
    coordinator: ExecutionCoordinator[VersionValue],
    registry: Registry[VersionValue],
    model_adapter: ModelAdapter,
    runtime_backend: BackendPort,
    runtime_environment: ExecutionEnvironment,
) -> Runner[VersionValue]:
    return Runner(
        coordinator=coordinator,
        adapter=model_adapter,
        backend=runtime_backend,
        middleware=(),
        environment=runtime_environment,
    )


@pytest.fixture
def reflector(
    model_adapter: ModelAdapter,
    migration_settings: MigrationSettings,
) -> Reflector[VersionValue]:
    return Reflector[VersionValue](
        model_adapter,
        Reflection[VersionValue](model_adapter, CompositeDiffDiscovery()),
        model_materializer=model_adapter,
        migration_materializer=MigrationMaterializer(JsonPatchMigrationBackend()),
        on_missing=migration_settings.on_missing,
    )


@pytest.fixture
def engine(
    registry: Registry,
    model_adapter: ModelAdapter,
) -> Engine[VersionValue]:
    return Engine(registry, model_adapter)


@pytest.fixture()
def manager(
    request: pytest.FixtureRequest,
    engine: Engine[VersionValue],
    migration_settings: MigrationSettings,
) -> type[Manager[VersionValue]]:
    namespace = getattr(request, "param", None)
    codec = getattr(engine.adapter, "model_codec", None)
    if namespace and codec is not None and codec.namespace != namespace:
        setattr(engine.adapter, "model_codec", replace(codec, namespace=namespace))
    return Manager[VersionValue].configure(
        engine.adapter,
        engine=engine,
        **manager_kwargs(migration_settings),
    )
