from __future__ import annotations

from typing import cast

import pytest

from pyverge import Manager
from pyverge.core import (
    DiscoverySettings,
    MigrationSettings,
    VersioningSettings,
)
from pyverge.migration import (
    CompoundKeyWalker,
    DefaultMigrationEntry,
    Engine,
    GraphBuilder,
    JsonSchemaModelAdapter,
    MigrationGraph,
    PydanticModelAdapter,
    PydanticWalker,
    Registry,
    SequentialExecutor,
)
from pyverge.types import (
    ModelAdapter,
    ModelBase,
    ResolverFactory,
    VersionValue,
    Walker,
)
from tests.utils import register_models
from tests.utils.engine import register_migrations
from tests.utils.settings import overrides

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
    return MigrationSettings(**overrides(custom))


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
) -> Registry[VersionValue, ModelBase]:
    _strategy, name, models, migrations = request.param
    registry = Registry[VersionValue, ModelBase](name=name)
    if models:
        register_models(model_adapter, registry, migration_settings, *models)
    if migrations:
        register_migrations(model_adapter, registry, *migrations)
    return registry


@pytest.fixture
def walker(
    registry: Registry[VersionValue, ModelBase],
    migration_settings: MigrationSettings,
    model_adapter: PydanticModelAdapter,
) -> Walker:
    """A preconfigured :class:`PydanticWalker` bound to the shared registry.

    Pass it to ``Manager[VersionValue].configure(settings, adapter, walker=...)``
    to drive container-guided discovery.
    """
    return PydanticWalker(
        registry,
        settings=migration_settings,
        adapter=model_adapter,
    )


@pytest.fixture
def graph_builder(
    registry: Registry[VersionValue, ModelBase],
    migration_settings: MigrationSettings,
    model_adapter: ModelAdapter,
) -> GraphBuilder[VersionValue]:
    """Return a graph builder with the standard compound-key walker."""
    return GraphBuilder(
        registry,
        migration_settings,
        CompoundKeyWalker(registry, settings=migration_settings, adapter=model_adapter),
    )


@pytest.fixture
def migration_graph(
    request: pytest.FixtureRequest,
    graph_builder: GraphBuilder[VersionValue],
    registry: Registry[VersionValue, ModelBase],
) -> MigrationGraph[VersionValue]:
    resolver_factory, payload = cast("tuple[ResolverFactory, dict]", request.param)
    return graph_builder.build(
        payload,
        target_resolver=resolver_factory(registry),
    )


@pytest.fixture
def engine(
    registry: Registry,
    migration_settings: MigrationSettings,
    model_adapter: ModelAdapter,
) -> Engine[VersionValue]:
    return cast(
        "Engine[VersionValue]",
        Engine(
            registry,
            migration_settings,
            SequentialExecutor(),
            GraphBuilder(
                registry,
                migration_settings,
                CompoundKeyWalker(
                    registry, settings=migration_settings, adapter=model_adapter
                ),
            ),
            model_adapter,
            entry_migration=DefaultMigrationEntry(),
        ),
    )


@pytest.fixture
def manager(
    engine: Engine[VersionValue],
) -> type[Manager[VersionValue]]:
    return Manager[VersionValue].configure(
        engine.settings, engine.adapter, engine=engine
    )
