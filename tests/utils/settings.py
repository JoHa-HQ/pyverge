"""Application-side test preset, not a library settings contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class MigrationSettings:
    """Flat test preset for constructing library components explicitly."""

    version_property: str = "version"
    kind_property: str = "kind"
    max_migration_depth: int = -1
    validation_mode: Literal["strict", "lax", "none"] = "lax"
    on_missing_field: Literal["raise", "skip"] = "raise"
    on_extra_field: Literal["raise", "ignore"] = "ignore"
    direction: Literal["any", "forward", "backward"] = "any"
    on_direction_violation: Literal["skip", "raise"] = "skip"
    on_missing_path: Literal["skip", "raise"] = "raise"
    on_missing: Literal[
        "reconstruct_model", "reconstruct_migration", "raise", "skip"
    ] = "raise"
    parallel_workers: int = 0
    execution_mode: Literal["sync", "async"] = "sync"


def overrides(options: dict[str, Any]) -> dict[str, Any]:
    return dict(options)


def without_identity(options: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in options.items()
        if key not in {"version_property", "kind_property"}
    }


VersioningSettings = MigrationSettings
DiscoverySettings = MigrationSettings


def manager_kwargs(settings: MigrationSettings) -> dict[str, Any]:
    """Build-time manager parameters only."""
    return {"on_missing": settings.on_missing}


__all__ = [
    "MigrationSettings",
    "VersioningSettings",
    "manager_kwargs",
    "overrides",
    "without_identity",
]
