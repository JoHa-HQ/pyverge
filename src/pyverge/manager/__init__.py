"""Public manager facade for pyverge.

Exposes the :class:`Manager` class factory together with the registration
descriptors it relies on.
"""

from .descriptors import (
    ManagerMeta,
    _HookDescriptor,
    _MigrationDescriptor,
    _ModelDescriptor,
)
from .manager import Manager

__all__ = [
    "Manager",
    "ManagerMeta",
    "_HookDescriptor",
    "_MigrationDescriptor",
    "_ModelDescriptor",
]
