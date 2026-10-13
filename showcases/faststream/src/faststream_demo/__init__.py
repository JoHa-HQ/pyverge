"""FastStream + pyverge showcase.

A runnable pyverge example: versioned message bodies converge to a policy target
before a FastStream subscriber handler runs.
"""

from .adapters import build_app, build_broker
from .domain import ALL_VERSIONS, ANCHOR_MODEL, ANCHOR_VERSION, Order, build_manager

__all__ = [
    "ALL_VERSIONS",
    "ANCHOR_MODEL",
    "ANCHOR_VERSION",
    "Order",
    "build_app",
    "build_broker",
    "build_manager",
]
