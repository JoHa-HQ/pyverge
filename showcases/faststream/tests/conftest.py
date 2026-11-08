from collections.abc import Callable
from typing import Any

import pytest


@pytest.fixture
def container():
    from faststream_demo.container import Container  # noqa: PLC0415

    return Container()


@pytest.fixture
def app(container):
    return container.app()


@pytest.fixture
def order_v1() -> Callable[..., dict[str, Any]]:
    """Factory fixture generating v1 order payloads with customizable fields."""

    def _factory(
        order_id: str = "order-1",
        total: float = 100.0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": "Order",
            "version": "1.0.0",
            "order_id": order_id,
            "total": total,
            "address": {
                "kind": "Address",
                "version": "1.0.0",
                "street": "5th Avenue",
                "city": "New York",
            },
        }
        payload.update(kwargs)
        return payload

    return _factory
