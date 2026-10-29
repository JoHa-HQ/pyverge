from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from typing import Any, cast

import pytest

from pyverge import Manager
from pyverge.core.clock import SystemClock
from pyverge.core.ids import UuidIdFactory
from pyverge.core.types import (
    VersionValue,
)
from pyverge.discovery.reflection import (
    CompositeDiffDiscovery,
    Reflection,
    Reflector,
)
from pyverge.engine import Engine
from pyverge.execution import (
    AnyDirection,
    CompositeExtractor,
    ExecutionCoordinator,
    ExecutionPlanner,
    PathResolver,
    PolicyEngine,
    Runner,
    TargetCompiler,
)
from pyverge.execution.backends import ThreadedBackend
from pyverge.execution.context import ExecutionEnvironment
from pyverge.execution.types import BackendPort
from pyverge.migrations.backend import MigrationMaterializer
from pyverge.migrations.identity import DefaultMigrationIdentityResolver
from pyverge.migrations.json_patch.backend import JsonPatchMigrationBackend
from pyverge.registry import Registry
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
from pyverge.versioning import DiffMaterializer, default_content_hasher
from tests.utils import edge_from_nodes, envelope_model, register_models
from tests.utils.engine import register_migrations
from tests.utils.source import StaticSource

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
            namespace="",
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
            namespace="",
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


@pytest.fixture
def node(
    request: pytest.FixtureRequest,
    versioning_settings: VersioningSettings,
) -> Any:
    adapter_cls, model = request.param
    adapter = adapter_cls(
        codec=ModelCodec(
            namespace="",
            version_property=versioning_settings.version_property,
            kind_property=versioning_settings.kind_property,
        )
    )
    result = envelope_model(adapter, versioning_settings, model)
    return result


@pytest.fixture
def edge(
    request: pytest.FixtureRequest,
    versioning_settings: VersioningSettings,
) -> VersionEdge:
    adapter_cls, source_model, target_model, func = request.param
    adapter = adapter_cls(
        codec=ModelCodec(
            namespace="",
            version_property=versioning_settings.version_property,
            kind_property=versioning_settings.kind_property,
        )
    )
    source = envelope_model(adapter, versioning_settings, source_model)
    target = envelope_model(adapter, versioning_settings, target_model)
    return edge_from_nodes(adapter, source, target, func=func)


@pytest.fixture(scope="function", params=[(VersionValue, "test", [], [])])
def registry(
    request: pytest.FixtureRequest,
    model_adapter: PydanticModelAdapter,
    migration_settings: MigrationSettings,
) -> Registry[VersionValue]:
    _strategy, name, models, migrations, *rest = request.param
    namespace = rest[0] if rest else ""
    if namespace and not model_adapter.model_codec.namespace:
        model_adapter.model_codec = replace(
            model_adapter.model_codec, namespace=namespace
        )
    registry = Registry[VersionValue](
        name=name,
        namespace=namespace,
        hasher=default_content_hasher(),
    )
    if models:
        register_models(model_adapter, registry, migration_settings, *models)
    if migrations:
        register_migrations(model_adapter, registry, *migrations)
    return registry


@pytest.fixture
def walker(
    registry: Registry[VersionValue],
    migration_settings: MigrationSettings,
    model_adapter: PydanticModelAdapter,
) -> CompositeExtractor:
    """A preconfigured :class:`CompositeExtractor` bound to the shared registry.

    Pass it to ``Manager[VersionValue].configure(settings, adapter, walker=...)``
    to drive container-guided discovery.
    """
    return CompositeExtractor(
        registry,
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


@pytest.fixture
def coordinator(
    walker: CompositeExtractor[VersionValue],
    registry: Registry[VersionValue],
) -> ExecutionCoordinator[VersionValue]:
    return ExecutionCoordinator(
        extractor=walker,
        paths=PathResolver(registry),
        policy=PolicyEngine(
            direction=AnyDirection(),
            on_direction_violation="raise",
            on_missing_path="raise",
            depth_limit=-1,
            on_depth_violation="raise",
        ),
        planner=ExecutionPlanner(),
    )


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
        target_compiler=TargetCompiler[VersionValue](registry, model_adapter),
    )


@pytest.fixture
def model_materializer(model_adapter: ModelAdapter) -> ModelAdapter:
    return model_adapter


@pytest.fixture
def migration_materializer(request: pytest.FixtureRequest) -> MigrationMaterializer:
    backend = getattr(request, "param", JsonPatchMigrationBackend)
    return MigrationMaterializer(backend())


@pytest.fixture
def reflector(
    model_adapter: ModelAdapter,
    model_materializer: ModelAdapter,
    migration_materializer: DiffMaterializer[object],
    migration_settings: MigrationSettings,
) -> Reflector[VersionValue]:
    return Reflector[VersionValue](
        model_adapter,
        Reflection[VersionValue](model_adapter, CompositeDiffDiscovery()),
        model_materializer=model_materializer,
        migration_materializer=migration_materializer,
        on_missing=migration_settings.on_missing,
    )


@pytest.fixture
def engine(
    registry: Registry,
    model_adapter: ModelAdapter,
    reflector: Reflector[VersionValue],
) -> Engine[VersionValue]:
    return Engine(
        registry,
        model_adapter,
        DefaultMigrationIdentityResolver(),
        reflector,
    )


@pytest.fixture
def source(request: pytest.FixtureRequest) -> StaticSource:
    """Build a static source from ``(descriptors, source_id)`` params."""
    descriptors, source_id = request.param
    return StaticSource(tuple(descriptors), source_id)


@pytest.fixture()
def manager(
    request: pytest.FixtureRequest,
    engine: Engine[VersionValue],
    migration_settings: MigrationSettings,
) -> type[Manager[VersionValue]]:
    namespace = getattr(request, "param", "")
    return Manager[VersionValue].configure(
        engine.adapter,
        engine=engine,
        namespace=namespace,
        **manager_kwargs(migration_settings),
    )
