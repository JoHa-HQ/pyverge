"""Migration descriptor reflection."""

from __future__ import annotations

from pyverge.discovery.types import (
    RegistrationContext,
    RegistrationPort,
    SourceDescriptor,
)
from pyverge.reflection import Reflector
from pyverge.versioning import VersionNode

_PAIR_LEN = 2
_PAIR_WITH_FLAG_LEN = 3


class MigrationStrategy:
    """Register migration pairs emitted by a source."""

    def reflect(
        self,
        descriptor: SourceDescriptor,
        *,
        registrar: RegistrationPort,
        reflector: Reflector,
        context: RegistrationContext,
    ) -> None:
        payload = descriptor.payload
        if not isinstance(payload, tuple):
            raise TypeError("migration descriptor payload must be a tuple")
        if len(payload) == _PAIR_LEN:
            pair, func = payload
            backward_compatible = False
        elif len(payload) == _PAIR_WITH_FLAG_LEN:
            pair, func, backward_compatible = payload
        else:
            raise ValueError("migration descriptor payload must have 2 or 3 items")
        resolved = tuple(
            item
            if isinstance(item, VersionNode)
            else registrar.adapter.versionable(item)
            for item in pair
        )
        registrar.store_migration(
            (resolved[0], resolved[1]),
            func,
            backward_compatible=backward_compatible,
        )


__all__ = ["MigrationStrategy"]
