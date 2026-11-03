from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pyverge.core.types import VersionValue
from pyverge.core.versioning import FieldDescriptor, NoDefault, VersionKey


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelCodec:
    """Identity policy shared by model adapters."""

    version_property: str
    kind_property: str
    namespace: str

    def __post_init__(self) -> None:
        if not self.namespace:
            raise ValueError("ModelCodec namespace must be non-empty")

    def version(self, fields: Mapping[str, FieldDescriptor]) -> str:
        return self._default(fields, self.version_property)

    def kind(self, fields: Mapping[str, FieldDescriptor]) -> str:
        return self._default(fields, self.kind_property)

    def version_key(
        self,
        *,
        kind: str,
        version: str | VersionValue,
    ) -> VersionKey[VersionValue]:
        return VersionKey[VersionValue].parse(self.namespace, kind, version)

    @staticmethod
    def _default(fields: Mapping[str, FieldDescriptor], name: str) -> str:
        descriptor = fields.get(name)
        if descriptor is None or isinstance(descriptor.default, NoDefault):
            return ""
        default = descriptor.default
        return default if isinstance(default, str) else str(default)


__all__ = ["ModelCodec"]
