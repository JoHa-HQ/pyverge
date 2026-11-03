from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Generic

from pyverge.core.types import VersionValue

from ..discovery import (
    AsyncSourcePort,
    DiscoveryReport,
    DiscoveryService,
    RegistrationContext,
    SourcePort,
)

if TYPE_CHECKING:
    from pyverge.runtime.manager.manager import Manager


class DiscoveryMixin(Generic[VersionValue]):
    """Manager-level source discovery and registration."""

    @classmethod
    def discover(
        cls: type[Manager[VersionValue]],
        source: SourcePort,
        *,
        context: RegistrationContext | None = None,
    ) -> DiscoveryReport:
        return DiscoveryService[VersionValue]().discover(
            source,
            target=cls,
            context=context,
        )

    @classmethod
    async def adiscover(
        cls: type[Manager[VersionValue]],
        source: AsyncSourcePort,
        *,
        context: RegistrationContext | None = None,
    ) -> DiscoveryReport:
        return await DiscoveryService[VersionValue]().adiscover(
            source,
            target=cls,
            context=context,
        )

    @classmethod
    def reflect(
        cls: type[Manager[VersionValue]],
        source: SourcePort,
        *,
        context: RegistrationContext | None = None,
    ) -> DiscoveryReport:
        warnings.warn(
            "Manager.reflect(source) is deprecated for source discovery; "
            "use Manager.discover(source)",
            DeprecationWarning,
            stacklevel=2,
        )
        return cls.discover(source, context=context)

    @classmethod
    async def areflect(
        cls: type[Manager[VersionValue]],
        source: AsyncSourcePort,
        *,
        context: RegistrationContext | None = None,
    ) -> DiscoveryReport:
        warnings.warn(
            "Manager.areflect(source) is deprecated for source discovery; "
            "use Manager.adiscover(source)",
            DeprecationWarning,
            stacklevel=2,
        )
        return await cls.adiscover(source, context=context)


__all__ = ["DiscoveryMixin"]
