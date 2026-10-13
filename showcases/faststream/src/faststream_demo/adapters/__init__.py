"""FastStream adapter layer: broker/app builders over the shipped adapter.

The convergence seam itself lives in ``pyverge.adapters.faststream``; this layer
only wires the demo's broker, app, and tracing.
"""

from .broker import BROKERS, build_app, build_broker
from .tracing import build_tracer_provider, make_migration_hooks

__all__ = [
    "BROKERS",
    "build_app",
    "build_broker",
    "build_tracer_provider",
    "make_migration_hooks",
]
