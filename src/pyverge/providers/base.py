from __future__ import annotations

import logging
from typing import Any, cast

import pendulum
from semver import Version

from pyverge.core.types import (
    ModelVersionKey,
    VersionValue,
)

logger = logging.getLogger(__name__)


class AbstractModelAdapter:
    """Shared adapter behavior: version parsing and property configuration.

    Provider-neutral: owns only version/kind property config and version
    parsing.  Field-walking (``references`` etc.) is provider-specific and
    lives in each concrete adapter.
    """

    def __init__(
        self,
        version_property: str = "version",
        kind_property: str = "kind",
    ) -> None:
        self._version_property = version_property
        self._kind_property = kind_property

    @property
    def version_property(self) -> str:
        """The field name carrying a model's version."""
        return self._version_property

    @property
    def kind_property(self) -> str:
        """The field name carrying a model's kind."""
        return self._kind_property

    def version(self, model_cls: type[Any]) -> str:
        """Return the model's version string. Implemented by concrete adapters."""
        raise NotImplementedError

    def kind(self, model_cls: type[Any]) -> str:
        """Return the model's kind. Implemented by concrete adapters."""
        raise NotImplementedError

    @classmethod
    def of(cls, value: str | VersionValue) -> VersionValue:
        """Parse a version string, or pass through an already-parsed value.

        Understands both semver and ISO date strings.  Idempotent: a
        ``semver.Version`` or ``pendulum.Date`` produced by a previous call is
        returned unchanged, so a value may cross the parse boundary more than
        once.
        """
        if isinstance(value, Version) or (
            isinstance(value, pendulum.Date)
            and not isinstance(value, pendulum.DateTime)
        ):
            return cast(VersionValue, value)

        if not isinstance(value, str):
            msg = f"Cannot parse version {value!r}: expected a string or VersionValue."
            raise TypeError(msg)

        try:
            return cast(VersionValue, Version.parse(value))
        except ValueError:
            logger.debug(f"Failed to parse semver: {value!r}")

        try:
            parsed = pendulum.parse(str(value), exact=True)
            if isinstance(parsed, pendulum.DateTime):
                parsed = parsed.date()
            if not isinstance(parsed, pendulum.Date):
                raise ValueError(f"Expected date, got {parsed!r}")
            return cast(VersionValue, parsed)
        except ValueError:
            logger.debug(f"Failed to parse date: {value!r}")

        msg = (
            f"Cannot parse version {value!r}. "
            "Expected semver (e.g. '1.0.0') or ISO date (e.g. '2024-06-01')."
        )
        raise ValueError(msg)

    def fields(self, model_cls: type[Any]) -> frozenset[str]:
        """Return the model's field names, minus the identity fields.

        The identity fields (``version``/``kind``, per the adapter's configured
        property names) are owned by the version graph, so they are excluded:
        two registrations of the same ``(kind, version)`` must agree on the
        *payload* surface, not on the identity encoding.
        """
        identity = {self._version_property, self._kind_property}
        fields = getattr(model_cls, "model_fields", None)
        if fields is None:
            return frozenset()
        return frozenset(name for name in fields if name not in identity)


_ = ModelVersionKey
