"""Target policy compilation branches."""

from __future__ import annotations

import pytest
import semver

from pyverge.execution.targets import (
    TargetCompiler,
    earliest_target_resolver,
    fixed_target_resolver,
    multi_target_resolver,
)
from pyverge.providers import PydanticModelAdapter
from pyverge.registry import Registry
from pyverge.registry.errors import CatalogError
from pyverge.versioning import default_content_hasher
from tests.examples.pydantic.semver import UserV1, UserV2


def _setup():
    adapter = PydanticModelAdapter()
    registry = Registry[semver.Version](hasher=default_content_hasher())
    source = adapter.versionable(UserV1)
    target = adapter.versionable(UserV2)
    registry.store_model(source)
    registry.store_model(target)
    compiler = TargetCompiler(registry, adapter)
    return adapter, registry, compiler, source, target


def test_target_compiler_policy_branches() -> None:
    _, _, compiler, source, target = _setup()
    assert compiler.compile(None)(source) is None
    assert compiler.compile("skip")(source) is None
    assert compiler.compile("latest")(source) == target
    assert compiler.compile("earliest")(source) == source
    assert compiler.compile("2.0.0")(source) == target
    assert compiler.compile(UserV2)(source) == target
    assert compiler.compile({"User": "2.0.0"})(source) == target
    assert compiler.compile({"*": "2.0.0"})(source) == target
    assert compiler.compile(target)(source) == target
    assert compiler.compile(lambda current: target)(source) is target


def test_target_compiler_errors() -> None:
    adapter, registry, compiler, _, _ = _setup()
    with pytest.raises(CatalogError, match="Could not resolve"):
        compiler.compile("not-a-version")
    with pytest.raises(CatalogError, match="not registered"):
        compiler.compile(int)
    with pytest.raises(CatalogError, match=r"Target .* not registered"):
        fixed_target_resolver(
            registry, adapter.version_key(kind="User", version="9.0.0")
        )


def test_multi_target_without_fallback_returns_none() -> None:
    _, _, _, source, _ = _setup()
    assert multi_target_resolver({})(source) is None


def test_earliest_target_resolver() -> None:
    _, registry, _, source, _ = _setup()
    assert earliest_target_resolver(registry)(source) == source
