from __future__ import annotations

from typing import cast

import pytest

from pyverge import Manager
from pyverge.core.types import (
    VersionValue,
)
from pyverge.manager.types import (
    ResolverFactory,
)
from pyverge.migration import (
    CompoundKeyWalker,
    Engine,
    GraphBuilder,
    JsonSchemaModelAdapter,
    MigrationGraph,
    PydanticModelAdapter,
    PydanticWalker,
    Registry,
)
from pyverge.migration.types import (
    Walker,
)
from pyverge.migrations.identity import DefaultMigrationIdentityResolver
from pyverge.migrations.json_patch.backend import JsonPatchMigrationBackend
from pyverge.providers.types import (
    ModelAdapter,
)
from pyverge.reflection import CompositeDiffDiscovery, Reflection
from pyverge.schemas.backend import ModelMaterializer
from pyverge.versioning import default_content_hasher
from tests.utils import register_models
from tests.utils.engine import register_migrations
from tests.utils.settings import (
    DiscoverySettings,
    MigrationSettings,
    VersioningSettings,
    manager_kwargs,
    overrides,
    without_identity,
)

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
        version_property=versioning_settings.version_property,
        kind_property=versioning_settings.kind_property,
    )


@pytest.fixture
def json_model_adapter(
    versioning_settings: VersioningSettings,
) -> JsonSchemaModelAdapter:
    return JsonSchemaModelAdapter(
        version_property=versioning_settings.version_property,
        kind_property=versioning_settings.kind_property,
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


@pytest.fixture(scope="function", params=[(VersionValue, "test", [], [])])
def registry(
    request: pytest.FixtureRequest,
    model_adapter: PydanticModelAdapter,
    migration_settings: MigrationSettings,
) -> Registry[VersionValue]:
    _strategy, name, models, migrations = request.param
    registry = Registry[VersionValue](name=name, hasher=default_content_hasher())
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
) -> Walker:
    """A preconfigured :class:`PydanticWalker` bound to the shared registry.

    Pass it to ``Manager[VersionValue].configure(settings, adapter, walker=...)``
    to drive container-guided discovery.
    """
    return PydanticWalker(
        registry,
        adapter=model_adapter,
        validation_mode=migration_settings.validation_mode,
        direction=migration_settings.direction,
    )


@pytest.fixture
def graph_builder(
    registry: Registry[VersionValue],
    migration_settings: MigrationSettings,
    model_adapter: ModelAdapter,
) -> GraphBuilder[VersionValue]:
    """Return a graph builder with the standard compound-key walker."""
    return GraphBuilder(
        registry,
        CompoundKeyWalker(
            registry,
            adapter=model_adapter,
            validation_mode=migration_settings.validation_mode,
            direction=migration_settings.direction,
        ),
        max_migration_depth=migration_settings.max_migration_depth,
    )


@pytest.fixture
def migration_graph(
    request: pytest.FixtureRequest,
    graph_builder: GraphBuilder[VersionValue],
    registry: Registry[VersionValue],
) -> MigrationGraph[VersionValue]:
    resolver_factory, payload = cast("tuple[ResolverFactory, dict]", request.param)
    return graph_builder.build(
        payload,
        target_resolver=resolver_factory(registry),
    ).graph


@pytest.fixture
def engine(
    registry: Registry,
    migration_settings: MigrationSettings,
    model_adapter: ModelAdapter,
) -> Engine[VersionValue]:
    return Engine(
        registry,
        model_adapter,
        DefaultMigrationIdentityResolver(),
        {
            "reconstruct_model": ModelMaterializer(model_adapter),
            "reconstruct_migration": JsonPatchMigrationBackend(),
        },
        Reflection(model_adapter, CompositeDiffDiscovery()),
        on_missing=migration_settings.on_missing,
    )


@pytest.fixture
def manager(
    engine: Engine[VersionValue],
    migration_settings: MigrationSettings,
) -> type[Manager[VersionValue]]:
    return Manager[VersionValue].configure(
        engine.adapter,
        engine=engine,
        **manager_kwargs(migration_settings),
    )
