"""Versioning error construction."""

from __future__ import annotations

from pyverge.providers import PydanticModelAdapter
from pyverge.versioning.errors import (
    BackwardCompatibilityError,
    MigrationApplicationError,
)
from tests.examples.pydantic.semver import UserV1, UserV2


def test_migration_application_error_legacy_pair() -> None:
    adapter = PydanticModelAdapter()
    source = adapter.versionable(UserV1)
    target = adapter.versionable(UserV2)
    error = MigrationApplicationError((source, target))
    assert error.kind == "unknown"
    assert error.source is source
    assert error.target is target
    assert error.reason is None
    assert str(error) == f"Migration failed: {source} → {target}"


def test_migration_application_error_with_reason() -> None:
    adapter = PydanticModelAdapter()
    source = adapter.versionable(UserV1)
    target = adapter.versionable(UserV2)
    error = MigrationApplicationError("User", source, target, reason="boom")
    assert error.kind == "User"
    assert error.reason == "boom"
    assert str(error).endswith(": boom")


def test_backward_compatibility_error_details() -> None:
    adapter = PydanticModelAdapter()
    source = adapter.versionable(UserV1)
    target = adapter.versionable(UserV2)
    error = BackwardCompatibilityError(
        "test",
        (source, target),
        removed=("name",),
        modified=("email",),
        required_additions=("age",),
    )
    message = str(error)
    assert "removed=['name']" in message
    assert "modified=['email']" in message
    assert "required_additions=['age']" in message
