"""Utility context managers for testing."""

import sys
import types
from typing import Any

from pyverge import Manager


class ManagerContext:
    """Context manager for registering a manager in a temporary module."""

    def __init__(self, manager_name: str, manager: Manager[Any]):
        self.manager_name = manager_name
        self.manager = manager
        self.module = None

    def __enter__(self):
        """Register the manager in a temporary module."""
        self.module = types.ModuleType(self.manager_name)
        setattr(self.module, "manager", self.manager)
        sys.modules[self.manager_name] = self.module
        return self.manager

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool | None:
        """Unregister the manager from the module."""
        if self.manager_name in sys.modules:
            del sys.modules[self.manager_name]
        return False  # Propagate exceptions if any
