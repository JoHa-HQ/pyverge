from dependency_injector import containers, providers
from faststream import FastStream

from .app import create_app
from .application import InMemoryAuditLog, InMemoryInvoiceLedger


class Container(containers.DeclarativeContainer):
    ledger = providers.Singleton(InMemoryInvoiceLedger)
    audit = providers.Singleton(InMemoryAuditLog)

    app: providers.Factory[FastStream] = providers.Factory(
        create_app,
        ledger=ledger,
        audit=audit,
    )
