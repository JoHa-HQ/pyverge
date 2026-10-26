from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, ClassVar, cast

import pendulum
from semver import Version

from pyverge.core.types import (
    ModelHandle,
    ModelVersionKey,
    VersionValue,
)
from pyverge.schemas.diff import FieldDescriptor
from pyverge.schemas.errors import ProviderCapabilityError
from pyverge.versioning import FrozenMap, ModelDescriptor, ModelRef

logger = logging.getLogger(__name__)


class AbstractModelAdapter:
    """Shared adapter behavior: version parsing and property configuration.

    Provider-neutral: owns only version/kind property config and version
    parsing.  Field-walking (``references`` etc.) is provider-specific and
    lives in each concrete adapter.
    """

    provider: ClassVar[str] = "custom"

    def __init__(
        self,
        version_property: str = "version",
        kind_property: str = "kind",
    ) -> None:
        self._version_property = version_property
        self._kind_property = kind_property

    @property
    def version_property(self) -> str:
        return self._version_property

    @property
    def kind_property(self) -> str:
        return self._kind_property

    def model_id(self, handle: ModelHandle) -> str:
        module = getattr(handle, "__module__", None) or type(handle).__module__
        qualname = getattr(handle, "__qualname__", None) or getattr(
            handle, "__name__", None
        )
        if qualname is None:
            return f"{module}.{type(handle).__qualname__}"
        return f"{module}.{qualname}"

    def model_descriptor(self, handle: ModelHandle) -> ModelDescriptor:
        identity = {self._version_property, self._kind_property}
        fields: dict[str, FieldDescriptor] = {
            name: descriptor
            for name, descriptor in self.describe_fields(handle).items()
            if name not in identity
        }
        return ModelDescriptor(
            ref=ModelRef(
                provider=self.provider,
                model_id=self.model_id(handle),
            ),
            fields=FrozenMap(fields),
        )

    def version(self, model_cls: type[Any]) -> str:
        raise NotImplementedError

    def kind(self, model_cls: type[Any]) -> str:
        raise NotImplementedError

    def describe_fields(self, model_cls: ModelHandle) -> Mapping[str, FieldDescriptor]:
        raise NotImplementedError

    def references(self, model_cls: ModelHandle) -> frozenset[ModelVersionKey]:
        raise NotImplementedError

    @classmethod
    def of(cls, value: str | VersionValue) -> VersionValue:
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

    def can_handle(
        self,
        container: Any,
        *,
        fields: frozenset[str] | None = None,
    ) -> bool:
        raise NotImplementedError

    def ensure_compatible(
        self,
        container: Any,
        *,
        fields: frozenset[str],
    ) -> None:
        if container is None:
            return
        if not self.can_handle(container, fields=fields):
            raise ProviderCapabilityError(
                "container is incompatible with the migration graph: "
                f"cannot cover fields {sorted(fields)}"
            )

    def fields(self, model_cls: type[Any]) -> frozenset[str]:
        identity = {self._version_property, self._kind_property}
        fields = getattr(model_cls, "model_fields", None)
        if fields is None:
            return frozenset()
        return frozenset(name for name in fields if name not in identity)
