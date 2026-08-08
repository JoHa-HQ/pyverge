"""Tests for CLI manager resolution (config name and import-path forms)."""

from __future__ import annotations

import sys
import types

import pytest
import semver

from pyverge.cli.config import ConfigError, resolve_manager
from pyverge.migration import ModelManager, PydanticModelAdapter


def _manager() -> ModelManager[semver.Version]:
    return ModelManager[semver.Version].scoped(PydanticModelAdapter())()


def _register_module(name: str, manager: object) -> None:
    module = types.ModuleType(name)
    module.manager = manager
    sys.modules[name] = module


def test_resolve_manager_by_import_path() -> None:
    """A ``module:object_path`` spec resolves to the manager attribute."""
    mgr = _manager()
    _register_module("fake_pkg.container", mgr)

    assert resolve_manager("fake_pkg.container:manager") is mgr


def test_resolve_manager_nested_object_path() -> None:
    """A dotted object path navigates nested attributes (DI-style containers)."""
    mgr = _manager()
    container = types.SimpleNamespace()
    container.services = types.SimpleNamespace()
    container.services.user_manager = mgr

    module = types.ModuleType("fake_di")
    module.container = container
    sys.modules["fake_di"] = module

    assert resolve_manager("fake_di:container.services.user_manager") is mgr


def test_resolve_manager_by_config_name_missing_raises() -> None:
    """A config-name spec with no matching config raises ConfigError."""
    with pytest.raises(ConfigError):
        resolve_manager("nonexistent_manager")


def test_resolve_manager_non_manager_object_raises() -> None:
    """An object path that does not resolve to a ModelManager raises ConfigError."""
    _register_module("fake_notmanager", 123)

    with pytest.raises(ConfigError):
        resolve_manager("fake_notmanager:manager")
