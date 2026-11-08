from typing import Any

from .billing import Invoice


class InMemoryInvoiceLedger:
    """In-memory storage for issued invoices."""

    def __init__(self) -> None:
        self._invoices: list[Invoice] = []

    def record(self, invoice: Invoice) -> None:
        self._invoices.append(invoice)

    @property
    def invoices(self) -> list[Invoice]:
        return list(self._invoices)


class InMemoryAuditLog:
    """In-memory audit log for unhandled payloads."""

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []

    def record(self, payload: dict[str, Any]) -> None:
        self._entries.append(payload)

    @property
    def entries(self) -> list[dict[str, Any]]:
        return list(self._entries)
