"""Build-stage registration context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pyverge.core.clock import Clock


@dataclass(frozen=True, slots=True)
class RegistrationContext:
    """Context supplied to build-time visitors; never exposed to migrations."""

    source_id: str
    logger: Any
    clock: Clock
    validate_references: bool = True


__all__ = ["RegistrationContext"]
