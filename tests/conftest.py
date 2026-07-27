from __future__ import annotations

from pydantic_migrator.migration.models import VersioningSettings
import pytest
from typer.testing import CliRunner

from pydantic_migrator.migration import DiscoverySettings, MigrationSettings

# from tests.examples.nested_models import NestedModelManager
# from tests.examples.semver import SemverManager

# from tests.examples.eager import UserContainer as EagerUserContainer
# from tests.examples.eager import eager_manager


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# @pytest.fixture
# def application(runner: CliRunner) -> Callable[..., Result]:
#     return partial(runner.invoke, app)


@pytest.fixture
def versioning_settings() -> VersioningSettings:
    return VersioningSettings()


@pytest.fixture
def migration_settings() -> MigrationSettings:
    return MigrationSettings()


@pytest.fixture
def discovery_settings() -> DiscoverySettings:
    return DiscoverySettings()


# @pytest.fixture(scope="function")
# def default_registry() -> Registry:
#     return SemverManager.registry.copy()


# @pytest.fixture(scope="function")
# def nested_registry() -> Registry:
#     return NestedModelManager.registry.copy()


# @pytest.fixture
# def default_manager() -> DefaultManager:
#     return DefaultManager(ManagerSettings(version_property="version"))


# @pytest.fixture
# def eager_manager_instance() -> ModelManager[EagerUserContainer]:
#     return eager_manager


# @pytest.fixture
# def coordinator() -> Coordinator:  # pragma: no cover
#     """Coordinator with multiple model families"""
#     return Coordinator()
