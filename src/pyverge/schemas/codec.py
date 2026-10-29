from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from pyverge.core.types import VersionValue
from pyverge.versioning import (
    FieldDescriptor,
    NoDefault,
    VersionKey,
    parse_version,
)


@dataclass(frozen=True, slots=True)
class ModelCodec:
    """Identity policy shared by model adapters."""

    version_property: str = "version"
    kind_property: str = "kind"
    namespace: str = ""

    def of(self, value: str | VersionValue) -> VersionValue:
        return parse_version(value)

    def version(self, fields: Mapping[str, FieldDescriptor]) -> str:
        return self._default(fields, self.version_property)

    def kind(self, fields: Mapping[str, FieldDescriptor]) -> str:
        return self._default(fields, self.kind_property)

    def version_key(self, *, kind: str, version: str) -> VersionKey[VersionValue]:
        return VersionKey[VersionValue](
            namespace=self.namespace,
            kind=kind,
            version=cast("VersionValue", version),
        )

    @staticmethod
    def _default(fields: Mapping[str, FieldDescriptor], name: str) -> str:
        descriptor = fields.get(name)
        if descriptor is None or isinstance(descriptor.default, NoDefault):
            return ""
        default = descriptor.default
        return default if isinstance(default, str) else str(default)


__all__ = ["ModelCodec"]
