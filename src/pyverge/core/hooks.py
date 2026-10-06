from collections.abc import Mapping
from typing import Any

from .types import Comparable


class MigrationHook:
    """Base class for migration hooks.

    Hooks are read-only observers that allow you to inject custom behavior
    before, after, or on error during migrations.  Default implementations
    are no-ops — subclass and override only what you need.

    A provider-specific hook lives with its adapter — e.g.
    :class:`~pyverge.adapters.otel.OTELHook` for OpenTelemetry tracing.
    """

    def before_migrate(
        self,
        name: str,
        from_version: Comparable,
        to_version: Comparable,
        data: Mapping[str, Any],
    ) -> None: ...

    def after_migrate(
        self,
        name: str,
        from_version: Comparable,
        to_version: Comparable,
        original_data: Mapping[str, Any],
        migrated_data: Mapping[str, Any],
    ) -> None: ...

    def on_error(
        self,
        name: str,
        from_version: Comparable,
        to_version: Comparable,
        data: Mapping[str, Any],
        error: Exception,
    ) -> None: ...
