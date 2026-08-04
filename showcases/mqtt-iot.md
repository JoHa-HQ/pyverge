# MQTT / IoT Streaming

## Problem

Devices in the field report sensor readings with firmware-specific schemas.
Older firmware may omit fields newer dashboards require. Gateways and
dashboards need a single, current schema to aggregate and visualize telemetry.

## How converge helps

A gateway subscribes to per-device topics, converges each payload by `kind`,
and republishes it on a canonical topic. A per-fleet target policy keeps some
device families on an intermediate schema while the rest converge fully.

## Example flow

1. A device reports at firmware `1.0.0` with `kind=Order`.
2. Firmware `2.0.0` adds `currency`; a migration `1.0.0 → 2.0.0` is registered.
3. The gateway converges the payload and republishes it on `normalized/Order`.
4. Per-kind pins (e.g. `{"LegacySensor": "1.5.0", "*": "latest"}`) let legacy
   fleets lag intentionally — pinned kinds must be registered with the manager.

## Quick start (projected)

Uses the high-level `ModelManager` facade with a thin adapter around the
`paho-mqtt` driver. **Illustrative — the transport glue is not shipped.**

```python
import json
from typing import Literal

import semver
from pydantic import BaseModel

from pyverge.migration import MigrationSettings, ModelManager, PydanticModelAdapter

OrderManager = ModelManager.scoped(
    semver.Version,
    adapter=PydanticModelAdapter(),
    settings=MigrationSettings(direction="forward", on_missing_path="raise"),
)


@OrderManager.model()
class OrderV1(BaseModel):
    kind: Literal["Order"] = "Order"
    version: Literal["1.0.0"] = "1.0.0"
    order_id: str
    total: float


@OrderManager.model()
class OrderV2(BaseModel):
    kind: Literal["Order"] = "Order"
    version: Literal["2.0.0"] = "2.0.0"
    order_id: str
    total: float
    currency: str = "USD"


@OrderManager.migration("Order", "1.0.0", "2.0.0")
def add_currency(data: dict) -> dict:
    return {**data, "currency": "USD"}


manager = OrderManager()

# Projected — real driver: paho-mqtt. Not shipped.
import paho.mqtt.client as mqtt


class TelemetryGateway:
    """Adapts an MQTT client to converge device payloads on ingress."""

    def __init__(self, client: mqtt.Client, manager, target=None):
        self._client = client
        self._manager = manager
        self._target = target or {"*": "latest"}

    def on_telemetry(self, _client, _userdata, msg: mqtt.MQTTMessage) -> None:
        payload = json.loads(msg.payload)
        normalized = self._manager.migrate(payload, target=self._target)
        self._client.publish(f"normalized/{payload['kind']}", json.dumps(normalized))


gateway = TelemetryGateway(
    mqtt.Client(),
    manager,
    target={"LegacySensor": "1.5.0", "*": "latest"},
)
client.on_message = gateway.on_telemetry
```

## Abstractions used

- **ModelManager** — stateless facade; `manager.migrate(payload, target=...)`
  converges each device payload.
- **TelemetryGateway** — thin adapter; converge-and-forward with no per-device
  state.
- **Per-kind target** — a pin with a `"*"` fallback keeps legacy fleets on
  their firmware schema.

## Out of scope

- Broker subscriptions, QoS, and reconnect logic — owned by the MQTT client.
- Unit conversion — migrations change field names and add defaults; numeric
  conversions belong in explicit migration functions.
