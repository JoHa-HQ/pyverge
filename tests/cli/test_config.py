"""Tests for CLI manager resolution (config name and import-path forms)."""

from __future__ import annotations

import sys
import types

import pytest
import semver

from pyverge.cli.config import ConfigError, resolve_manager
from pyverge.migration import ModelManager, PydanticModelAdapter


@pytest.fixture
def manager() -> ModelManager[semver.Version]:
    return ModelManager[semver.Version].scoped(PydanticModelAdapter())()


def _register_module(name: str, attribute: str, value: object) -> None:
    """Register a fake importable module exposing ``attribute``."""
    module = types.ModuleType(name)
    setattr(module, attribute, value)
    sys.modules[name] = module


class TestResolveManagerByPath:
    """Resolution via ``module:object_path``."""

    def test_single_attribute_path(self, manager: ModelManager[semver.Version]) -> None:
        _register_module("fake_pkg.container", "manager", manager)

        assert resolve_manager("fake_pkg.container:manager") is manager

    def test_nested_object_path(
        self, manager: ModelManager[semver.Version]
    ) -> None:
        container = types.SimpleNamespace()
        container.services = types.SimpleNamespace()
        container.services.user_manager = manager
        _register_module("fake_di", "container", container)

        assert resolve_manager("fake_di:container.services.user_manager") is manager


class TestResolveManagerErrors:
    """Resolution failure modes."""

    def test_unknown_config_name_raises(self) -> None:
        with pytest.raises(ConfigError):
            resolve_manager("nonexistent_manager")

    def test_non_manager_object_raises(self) -> None:
        _register_module("fake_notmanager", "manager", 123)

        with pytest.raises(ConfigError):
            resolve_manager("fake_notmanager:manager")
