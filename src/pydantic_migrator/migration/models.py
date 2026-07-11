from dataclasses import dataclass, field
from typing import Generic, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from .types import MigrationDirectionStrategy, VersionValue


@dataclass(frozen=True, slots=True)
class ModelQuery(Generic[VersionValue]):
    """Encapsulates a lookup predicate for the registry.

    Exactly one predicate must be provided:
    - ``version_value``: match by version string (e.g., ``"1.2.3"``)
    - ``model_cls``: match by Pydantic model class (e.g., ``UserV2``)
    """

    version_value: VersionValue | None = field(
        default=None,
        metadata={"doc": "A specific version value to match."},
    )
    model_cls: type[BaseModel] | None = field(
        default=None,
        metadata={"doc": "A specific Pydantic model class to match."},
    )
    use_latest: bool = field(
        default=False,
        metadata={
            "doc": (
                "Whether to use the latest version. "
                "If the version or model value is not specified, the latest version will be used."
            )
        },
    )

    def __post_init__(self) -> None:
        if all((self.version_value is not None, self.model_cls is not None)):
            raise ValueError(
                "Provide exactly one of version_value or model_cls."
                f" Given two: version_value={self.version_value}, model_cls={self.model_cls}"
            )

    @property
    def predicate(self) -> VersionValue | type[BaseModel] | None:
        if self.version_value is not None:
            return cast(VersionValue, self.version_value)
        elif self.model_cls is not None:
            return cast(type[BaseModel], self.model_cls)
        elif self.use_latest:
            return None
        raise ValueError("Provide exactly one of version_value or model_cls.")


@dataclass(frozen=True, slots=True)
class MigrationQuery(Generic[VersionValue]):
    """Encapsulates a migration lookup predicate.

    Specify either *version_range* or *model_range*, not both.
    Consecutive elements are paired: ``(a, b, c)`` → ``(a→b, b→c)``.
    If *use_latest* is True and only one value given, the latest
    registered version is used as the target.
    """

    version_range: tuple[VersionValue, ...] = field(
        default=(),
        metadata={"doc": "Range of versions to migrate between."}
    )
    model_range: tuple[type[BaseModel], ...] = field(
        default=(),
        metadata={"doc": "Range of model classes to migrate between."}
    )
    use_latest: bool = field(
        default=False,
        metadata={"doc": "Whether to use the latest registered version as the target."}
    )

    def __post_init__(self) -> None:
        if self.version_range and self.model_range:
            raise ValueError(
                "Provide either version_range or model_range, not both"
            )

    @property
    def predicate(self) -> tuple[VersionValue, ...] | tuple[type[BaseModel], ...]:
        """Return the active range (version or model)."""
        if self.version_range:
            return self.version_range
        return self.model_range


class VersioningSettings(BaseModel):
    version_property: str = Field(
        default="version",
        description="Field name that holds the version on every model class.",
    )


class MigrationSettings(VersioningSettings):
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

    version_property: str = Field(
        default="version",
        description="Field name that holds the version on every model class.",
    )
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
    max_migration_depth: int = Field(
        default=-1,
        ge=-1,
        description=(
            "Maximum nesting depth to migrate. "
            "-1 = unlimited. 0 = top-level only. "
            "N = migrate up to N levels deep."
        ),
    )
