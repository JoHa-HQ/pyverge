from __future__ import annotations

from typing import cast

import pytest

from pyverge.core import (
    DiscoverySettings,
    MigrationSettings,
    VersioningSettings,
)
from pyverge.core.types import ModelAdapter, ModelBase, VersionValue, Walker
from pyverge.migration import (
    CompoundKeyWalker,
    DefaultMigrationEntry,
    Engine,
    GraphBuilder,
    JsonSchemaModelAdapter,
    ModelManager,
    PydanticModelAdapter,
    PydanticWalker,
    Registry,
    SequentialExecutor,
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


@pytest.fixture(params=[("provider")])
def model_adapter(
    request: pytest.FixtureRequest,
) -> PydanticModelAdapter | JsonSchemaModelAdapter:
    provider = request.param
    if provider == JsonSchemaModelAdapter:
        return request.getfixturevalue("json_model_adapter")
    if provider == PydanticModelAdapter:
        return request.getfixturevalue("pydantic_model_adapter")
    raise ValueError(f"Unknown provider: {provider}")


@pytest.fixture(scope="function", params=[("strategy", "name", "models", "migrations")])
def registry(
    request: pytest.FixtureRequest,
    model_adapter: PydanticModelAdapter,
    migration_settings: MigrationSettings,
) -> Registry[VersionValue, ModelBase]:
    strategy, name, models, migrations = request.param
    registry = Registry[strategy, ModelBase](name=name)
    if models:
        register_models(model_adapter, registry, migration_settings, *models)
    if migrations:
        register_migrations(model_adapter, registry, *migrations)
    return registry


@pytest.fixture
def walker(
    request: pytest.FixtureRequest,
    registry: Registry[VersionValue, ModelBase],
    migration_settings: MigrationSettings,
    model_adapter: PydanticModelAdapter,
) -> Walker:
    """Indirect fixture: a preconfigured walker built from ``request.param``.

    Parametrize with a walker class (e.g. ``PydanticWalker``) to obtain a
    walker bound to the shared ``registry``; pass it to
    ``ModelManager[VersionValue].scoped(walker=...)`` to drive
    container-guided discovery.
    """
    if request.param == PydanticWalker:
        return PydanticWalker(
            registry,
            settings=migration_settings,
            adapter=model_adapter,
        )

    raise ValueError(f"Unsupported walker type: {request.param}")


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
def engine(
    registry: Registry,
    migration_settings: MigrationSettings,
    graph_builder: GraphBuilder[VersionValue],
    model_adapter: ModelAdapter,
) -> Engine[VersionValue]:
    return Engine(
        registry,
        migration_settings,
        SequentialExecutor(),
        graph_builder,
        model_adapter,
        entry_migration=DefaultMigrationEntry(),
    )


@pytest.fixture
def manager(
    migration_settings: MigrationSettings,
    model_adapter: ModelAdapter,
    engine: Engine[VersionValue],
) -> type[ModelManager[VersionValue]]:
    return ModelManager[VersionValue].configure(
        migration_settings, model_adapter, engine=engine
    )
