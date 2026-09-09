from __future__ import annotations

import logging
from typing import cast

import pendulum
from semver import Version

from pyverge.core.types import VersionValue

logger = logging.getLogger(__name__)


class BaseModelAdapter:
    """Shared adapter behavior: version parsing and property configuration."""

    def __init__(
        self,
        version_property: str = "version",
        kind_property: str = "kind",
    ) -> None:
        self._version_property = version_property
        self._kind_property = kind_property

    @classmethod
    def of(cls, value: str) -> VersionValue:
        """Parse a version string (mostly coming from Literal), then determine the strategy"""  # noqa: E501
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
