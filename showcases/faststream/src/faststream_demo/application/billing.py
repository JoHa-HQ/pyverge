from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from ..domain import OrderV3

WHOLESALE_DISCOUNT = Decimal("0.10")
CENT = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class Invoice:
    """An invoice issued for a processed order."""

    order_id: str
    amount: Decimal
    currency: str
    shipping_country: str | None


def issue_invoice(order: OrderV3, discount: Decimal = Decimal(0)) -> Invoice:
    """Issue an invoice for the order, applying the discount to its amount."""
    amount = Decimal(str(order.amount)) * (1 - discount)
    return Invoice(
        order_id=order.order_id,
        amount=amount.quantize(CENT, rounding=ROUND_HALF_UP),
        currency=order.currency,
        shipping_country=order.address.country,
    )
