"""Remote execution adapters (future FaaS support)."""

from .transport import ExecutionTransport, StepRequest

__all__ = ["ExecutionTransport", "StepRequest"]
