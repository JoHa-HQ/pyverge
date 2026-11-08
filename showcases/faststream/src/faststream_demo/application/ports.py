from collections.abc import Sequence
from typing import Any, Protocol

from .billing import Invoice


class InvoiceLedger(Protocol):
    """Storage interface for issued invoices."""

    def record(self, invoice: Invoice) -> None: ...

    @property
    def invoices(self) -> Sequence[Invoice]: ...


class AuditLog(Protocol):
    """Storage interface for unhandled or unrecognized payloads."""

    def record(self, payload: dict[str, Any]) -> None: ...

    @property
    def entries(self) -> Sequence[dict[str, Any]]: ...
