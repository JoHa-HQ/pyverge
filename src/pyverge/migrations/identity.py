from __future__ import annotations

from typing import Protocol

from pyverge.core.types import MigrationFunc
from pyverge.versioning import MigrationIdentity


class MigrationIdentityResolver(Protocol):
    """Resolve a migration callable to a stable provider identity."""

    def resolve(self, func: MigrationFunc) -> MigrationIdentity: ...


class DefaultMigrationIdentityResolver:
    """Resolve declarative identities and named callables.

    Declarative migrations expose ``migration_identity``. Plain callables use
    ``__migration_id__`` or ``module.qualname``; anonymous callables use their
    source line as an explicit convenience identity.
    """

    def resolve(self, func: MigrationFunc) -> MigrationIdentity:
        declared = getattr(func, "migration_identity", None)
        if isinstance(declared, MigrationIdentity):
            return declared

        explicit = getattr(func, "__migration_id__", None)
        if isinstance(explicit, str) and explicit:
            return MigrationIdentity("callable", explicit)

        module = getattr(func, "__module__", None)
        qualname = getattr(func, "__qualname__", None)
        if not module or not qualname:
            raise ValueError(
                "Plain migration callables require a stable identity; "
                "set __migration_id__ or implement migration_identity"
            )

        code = getattr(func, "__code__", None)
        if "<lambda>" in qualname and code is not None:
            return MigrationIdentity(
                "callable", f"{module}.{qualname}:{code.co_firstlineno}"
            )
        return MigrationIdentity("callable", f"{module}.{qualname}")


__all__ = ["DefaultMigrationIdentityResolver", "MigrationIdentityResolver"]
