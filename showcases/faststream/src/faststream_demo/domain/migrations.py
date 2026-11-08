"""Migration functions between versions of the domain models."""

from pyverge.runtime import MigrationContext
from pyverge.types import ModelData


def add_country(data: ModelData, context: MigrationContext | None = None) -> ModelData:
    """Address 1.0.0 -> 2.0.0: the address began carrying a country."""
    return {**data, "country": None}


def add_currency_retail(
    data: ModelData, context: MigrationContext | None = None
) -> ModelData:
    """Order 1.0.0 -> 2.0.0, retail path: retail orders were priced in USD."""
    return {**data, "currency": "USD"}


def add_currency_wholesale(
    data: ModelData, context: MigrationContext | None = None
) -> ModelData:
    """Order 1.0.0 -> 2.0.0, wholesale path: wholesale orders were priced in EUR."""
    return {**data, "currency": "EUR"}


def drop_currency(
    data: ModelData, context: MigrationContext | None = None
) -> ModelData:
    """Order 2.0.0 -> 1.0.0: drop the currency for consumers pinned to 1.0.0."""
    result = dict(data)
    result.pop("currency")
    return result


def rename_total_to_amount(
    data: ModelData, context: MigrationContext | None = None
) -> ModelData:
    """Order 2.0.0 -> 3.0.0: the total field was renamed to amount."""
    result = dict(data)
    result["amount"] = result.pop("total")
    return result


def rename_amount_to_total(
    data: ModelData, context: MigrationContext | None = None
) -> ModelData:
    """Order 3.0.0 -> 2.0.0: rename amount back to total for 2.0.0 consumers."""
    result = dict(data)
    result["total"] = result.pop("amount")
    return result
