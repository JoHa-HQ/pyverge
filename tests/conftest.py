from __future__ import annotations

import pendulum
import pytest
import semver

from pyverge.migration import (
    DiscoverySettings,
    Engine,
    MigrationSettings,
    ModelManager,
    PydanticModelAdapter,
    Registry,
    VersioningSettings,
)
from tests.utils import make_engine

# from tests.examples.nested_models import NestedModelManager
# from tests.examples.semver import SemverManager

# from tests.examples.eager import UserContainer as EagerUserContainer
# from tests.examples.eager import eager_manager


@pytest.fixture
def versioning_settings(
    version_property: str = "version",
    kind_property: str = "kind",
) -> VersioningSettings:
    return VersioningSettings(
        version_property=version_property,
        kind_property=kind_property,
    )


@pytest.fixture
def model_adapter(versioning_settings: VersioningSettings) -> PydanticModelAdapter:
    return PydanticModelAdapter(
        version_property=versioning_settings.version_property,
        kind_property=versioning_settings.kind_property,
    )


@pytest.fixture
def migration_settings(
    version_property: str = "version",
    kind_property: str = "kind",
) -> MigrationSettings:
    return MigrationSettings(
        version_property=version_property,
        kind_property=kind_property,
    )


@pytest.fixture
def discovery_settings(
    version_property: str = "version",
    kind_property: str = "kind",
) -> DiscoverySettings:
    return DiscoverySettings(
        version_property=version_property, kind_property=kind_property
    )


@pytest.fixture(scope="function")
def semver_registry(name: str | None = None) -> Registry:
    return Registry[semver.Version](name=name)


@pytest.fixture(scope="function")
def date_registry(name: str | None = None) -> Registry:
    return Registry[pendulum.DateTime](name=name)


@pytest.fixture
def registry(request: pytest.FixtureRequest) -> Registry:
    if request.param == semver.Version:
        return request.getfixturevalue("semver_registry")
    elif request.param == pendulum.DateTime:
        return request.getfixturevalue("date_registry")
    else:
        raise ValueError(f"Unsupported registry type: {request.param}")


@pytest.fixture
def semver_manager(
    model_adapter: PydanticModelAdapter,
) -> type[ModelManager[semver.Version]]:
    return ModelManager.scoped(semver.Version, model_adapter)


@pytest.fixture
def chrono_manager(
    model_adapter: PydanticModelAdapter,
) -> type[ModelManager[pendulum.Date]]:
    return ModelManager.scoped(pendulum.Date, model_adapter)


@pytest.fixture
def manager(
    request: pytest.FixtureRequest,
) -> type[ModelManager]:
    if request.param == semver.Version:
        return request.getfixturevalue("semver_manager")
    elif request.param == pendulum.Date:
        return request.getfixturevalue("chrono_manager")
    else:
        raise ValueError(f"Unsupported manager strategy: {request.param}")


@pytest.fixture
def semver_engine(
    semver_registry: Registry, migration_settings: MigrationSettings
) -> Engine[semver.Version]:
    return make_engine(semver_registry, migration_settings)


@pytest.fixture
def date_engine(
    date_registry: Registry, migration_settings: MigrationSettings
) -> Engine[pendulum.DateTime]:
    return make_engine(date_registry, migration_settings)
