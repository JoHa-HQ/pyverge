from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

import pendulum
from semver import Version

from pyverge.core.types import VersionValue
from pyverge.versioning import FieldDescriptor, NoDefault, VersionKey

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ModelCodec:
    """Identity policy shared by model adapters."""

    version_property: str = "version"
    kind_property: str = "kind"

    def of(self, value: str | VersionValue) -> VersionValue:
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

    def version(self, fields: Mapping[str, FieldDescriptor]) -> str:
        return self._default(fields, self.version_property)

    def kind(self, fields: Mapping[str, FieldDescriptor]) -> str:
        return self._default(fields, self.kind_property)

    def version_key(self, *, kind: str, version: str) -> VersionKey[VersionValue]:
        return VersionKey[VersionValue](_value=self.of(version), _kind=kind)

    @staticmethod
    def _default(fields: Mapping[str, FieldDescriptor], name: str) -> str:
        descriptor = fields.get(name)
        if descriptor is None or isinstance(descriptor.default, NoDefault):
            return ""
        default = descriptor.default
        return default if isinstance(default, str) else str(default)


__all__ = ["ModelCodec"]
