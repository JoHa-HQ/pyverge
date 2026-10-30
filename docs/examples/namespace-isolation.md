# Namespace isolation

```python
from typing import Literal

import semver
from pydantic import BaseModel

from pyverge import Manager
from pyverge.schemas import ModelCodec, PydanticModelAdapter


def adapter(namespace: str) -> PydanticModelAdapter:
    return PydanticModelAdapter(
        codec=ModelCodec(
            namespace=namespace,
            version_property="version",
            kind_property="kind",
        )
    )


Orders = Manager[semver.Version].configure(adapter("com.acme.orders"))
Billing = Manager[semver.Version].configure(adapter("com.acme.billing"))


@Orders.model()
class OrdersUser(BaseModel):
    kind: Literal["User"] = "User"
    version: Literal["1.0.0"] = "1.0.0"
    name: str


@Billing.model()
class BillingUser(BaseModel):
    kind: Literal["User"] = "User"
    version: Literal["1.0.0"] = "1.0.0"
    name: str


orders = Orders()
billing = Billing()

assert orders.get("User", "1.0.0").namespace == "com.acme.orders"
assert billing.get("User", "1.0.0").namespace == "com.acme.billing"
assert orders.registry.namespace == "com.acme.orders"
assert billing.registry.namespace == "com.acme.billing"
```
