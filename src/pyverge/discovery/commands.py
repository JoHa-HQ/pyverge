from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pyverge.core.types import MigrationFunc, ModelHandle
from pyverge.versioning import VersionNode, VersionPair


class ModelRegistrationMode(StrEnum):
    """How a model registration handles an existing version."""

    STRICT = "strict"
    RECONCILE = "reconcile"


@dataclass(frozen=True, slots=True)
class MigrationSpec:
    """A normalized migration descriptor payload."""

    pair: VersionPair[Any]
    func: MigrationFunc
    backward_compatible: bool = False


@dataclass(frozen=True, slots=True)
class RegisterModel:
    """Register one provider model handle."""

    payload: ModelHandle
    mode: ModelRegistrationMode


@dataclass(frozen=True, slots=True)
class RegisterVersion:
    """Register one already-materialized version node."""

    payload: VersionNode[Any]
    mode: ModelRegistrationMode


@dataclass(frozen=True, slots=True)
class RegisterMigration:
    """Register one normalized migration."""

    spec: MigrationSpec


__all__ = [
    "MigrationSpec",
    "ModelRegistrationMode",
    "RegisterMigration",
    "RegisterModel",
    "RegisterVersion",
]
