"""Additional graph variants for the CI showcase."""

from .chain import build_chain_manager
from .declarative import build_declarative_manager
from .key_only import build_key_only_registry
from .namespaces import build_billing_manager, build_orders_manager

__all__ = [
    "build_billing_manager",
    "build_chain_manager",
    "build_declarative_manager",
    "build_key_only_registry",
    "build_orders_manager",
]
