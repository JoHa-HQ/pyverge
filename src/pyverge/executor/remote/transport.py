"""Remote execution contract for FaaS backends (Lambda, Step Functions, ...)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from pyverge.core.types import ModelData


@dataclass(frozen=True, slots=True)
class StepRequest:
    """Serializable request for executing one migration step remotely."""

    kind: str
    from_version: str
    to_version: str
    payload: ModelData
    context: Mapping[str, Any]


class ExecutionTransport(Protocol):
    """Port for a remote FaaS transport."""

    def invoke(self, request: StepRequest) -> ModelData: ...

    async def ainvoke(self, request: StepRequest) -> ModelData: ...
