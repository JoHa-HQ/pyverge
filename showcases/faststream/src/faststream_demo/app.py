from collections.abc import Callable
from typing import Annotated, Any

from faststream import Context, FastStream
from faststream.kafka import KafkaBroker

from pyverge.adapters.faststream import Migration, Migrations, PyvergeBroker

from .application import (
    WHOLESALE_DISCOUNT,
    AuditLog,
    InvoiceLedger,
    issue_invoice,
)
from .domain import (
    OrderV3,
    add_country,
    add_currency_retail,
    add_currency_wholesale,
    drop_currency,
    rename_amount_to_total,
    rename_total_to_amount,
)

ORDER_MIGRATIONS = Migrations(
    Migration("Order", "1.0.0", "2.0.0", add_currency_retail, discriminator="retail"),
    Migration(
        "Order", "1.0.0", "2.0.0", add_currency_wholesale, discriminator="wholesale"
    ),
    Migration("Order", "2.0.0", "3.0.0", rename_total_to_amount),
    Migration("Order", "3.0.0", "2.0.0", rename_amount_to_total),
    Migration("Order", "2.0.0", "1.0.0", drop_currency),
    Migration("Address", "1.0.0", "2.0.0", add_country),
)

broker = PyvergeBroker(KafkaBroker())
app = FastStream(broker, lifespan=broker.lifespan)

orders = broker.subscriber("orders")


def is_type(value: str) -> Callable[[Any], bool]:
    """Filter messages by their type header."""
    return lambda msg: msg.headers.get("type") == value


@orders.handler(filter=is_type("retail"), discriminator="retail")
@broker.publish_to(routes={"orders.legacy": "1.0.0", "orders.current": "3.0.0"})
async def handle_retail(
    order: Annotated[OrderV3, ORDER_MIGRATIONS],
    ledger: InvoiceLedger = Context(),
) -> OrderV3:
    """Retail orders: issue an invoice at full price, then publish the order."""
    ledger.record(issue_invoice(order))
    return order


@orders.handler(filter=is_type("wholesale"), discriminator="wholesale")
async def handle_wholesale(
    order: Annotated[OrderV3, ORDER_MIGRATIONS],
    ledger: InvoiceLedger = Context(),
) -> None:
    """Wholesale orders: issue an invoice with the wholesale discount."""
    ledger.record(issue_invoice(order, WHOLESALE_DISCOUNT))


@orders.handler(converge=False)
async def handle_other(
    payload: dict[str, Any],
    audit: AuditLog = Context(),
) -> None:
    """Any other message: keep it aside as unhandled in the audit log."""
    audit.record(payload)


replies = broker.subscriber("orders.requests")


@replies.handler()
@broker.publisher("orders.replies", negotiator="accept-version")
async def reply(order: Annotated[OrderV3, ORDER_MIGRATIONS]) -> OrderV3:
    """Reply in the version the requester asked for in accept-version."""
    return order


def create_app(ledger: InvoiceLedger, audit: AuditLog) -> FastStream:
    """Bind storages to the application context and return the ready app."""
    app.context.set_global("ledger", ledger)
    app.context.set_global("audit", audit)
    return app
