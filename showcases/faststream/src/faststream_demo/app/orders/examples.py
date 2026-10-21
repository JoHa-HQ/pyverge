"""Ready-to-publish CloudEvent examples for the CLIs and tests."""

from __future__ import annotations

from typing import Any

ORDER_EXAMPLES: dict[str, dict[str, Any]] = {
    "v1": {
        "specversion": "1.0",
        "id": "1b4e28ba-2fa1-11d2-883f-0016d3cca427",
        "source": "/pyverge/showcase",
        "type": "com.pyverge.order.created",
        "datacontenttype": "application/json",
        "time": "2026-10-13T12:00:00Z",
        "data": {
            "kind": "Order",
            "version": "1.0.0",
            "order_id": "ord_101",
            "total": 99.5,
            "address": {
                "kind": "Address",
                "version": "1.0.0",
                "street": "Main St 1",
                "city": "Berlin",
            },
        },
    },
    "v2": {
        "specversion": "1.0",
        "id": "2c5f39cb-3ab2-22e3-994a-1127e4ddb538",
        "source": "/pyverge/showcase",
        "type": "com.pyverge.order.created",
        "datacontenttype": "application/json",
        "time": "2026-10-13T12:01:00Z",
        "data": {
            "kind": "Order",
            "version": "2.0.0",
            "order_id": "ord_102",
            "total": 99.5,
            "currency": "EUR",
            "address": {
                "kind": "Address",
                "version": "2.0.0",
                "street": "Main St 1",
                "city": "Berlin",
                "country": "DE",
            },
        },
    },
}

__all__ = ["ORDER_EXAMPLES"]
