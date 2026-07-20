from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .types import MigrationDirectionStrategy


class VersioningSettings(BaseModel):
    kind_property: str = Field(
        default="kind",
        description="Field name that holds the model family identifier (e.g., 'Address').",
    )
    version_property: str = Field(
        default="version",
        description="Field name that holds the version on every model class.",
    )


class DiscoverySettings(VersioningSettings):
    """Configuration for payload discovery — used by the graph builder.

    Controls what constitutes a versioned entry in the payload and
    how deep the discovery walker should traverse.
    """

    max_migration_depth: int = Field(
        default=-1,
        ge=-1,
        description=(
            "Maximum nesting depth to discover. "
            "-1 = unlimited. 0 = top-level only. "
            "N = discover up to N levels deep."
        ),
    )


class MigrationSettings(DiscoverySettings):
    """Configuration for migration behavior.

    Controls how the engine discovers version fields, which directions
    nested entries are allowed to migrate, and how violations are handled.

    Example:
        .. code-block:: python

            from pydantic_migrator.migration.settings import MigrationSettings

            config = MigrationSettings(
                version_property="version",
                direction="forward",
                on_direction_violation="raise",
                mode="streaming",
                parallel_workers=4,
            )
    """

    model_config = ConfigDict(extra="forbid")

    direction: MigrationDirectionStrategy = Field(
        default="any",
        description=(
            "Allowed migration directions for nested entries. "
            "'forward' — only source < target. "
            "'backward' — only source > target. "
            "'any' — both directions."
        ),
    )
    on_direction_violation: Literal["skip", "raise"] = Field(
        default="skip",
        description=(
            "What to do when a nested entry's direction is blocked by 'direction'. "
            "'skip' — silently leave the entry as-is. "
            "'raise' — fail before any migration."
        ),
    )
    on_missing_path: Literal["skip", "raise"] = Field(
        default="raise",
        description=(
            "What to do when no migration path exists for a nested entry. "
            "'skip' — silently leave the entry as-is. "
            "'raise' — fail before any migration."
        ),
    )
    mode: Literal["sequential", "streaming"] = Field(
        default="sequential",
        description=(
            "Payload traversal mode. "
            "'sequential' — collect all entries, migrate depth-grouped. "
            "'streaming' — yield entries one at a time (lower memory)."
        ),
    )
    parallel_workers: int = Field(
        default=0,
        ge=0,
        description=(
            "Number of worker threads for concurrent discovery. "
            "0 = sequential. Capped at ``os.cpu_count()``. "
            "Applies to either mode."
        ),
    )
    target_strategy: Literal["latest"] = Field(
        default="latest",
        description=(
            "Convergence target for discovered entries. "
            "'latest' — converge each entry to the highest "
            "registered version for its model type."
        ),
    )
