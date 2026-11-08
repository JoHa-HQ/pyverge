# FastStream showcase

A showcase demonstrating pyverge's declarative FastStream adapter: message bodies converge upstream through type annotations, with multi-target fan-out and header-based negotiation.

| Kind | Role | Graph |
| --- | --- | --- |
| `Order` | Root entity | v1 `total` → v2 `+currency` (USD/EUR by discriminator) → v3 `total` → `amount` |
| `Address` | Nested entity | v1 `street, city` → v2 `+country` |

## Architecture

- `domain/` — anchor models (`OrderV3`, `AddressV2`) and migration functions. Pure Python, no transport or framework dependencies.
- `application/` — business logic (invoicing, wholesale discount) and storage interfaces (`InvoiceLedger`, `AuditLog`).
- `app.py` — FastStream application wiring handlers, subscribers, and publishers via `PyvergeBroker`.
- `container.py` — `dependency-injector` composition root.

## Channels & routing

- `orders` — input topic with multiple handlers:
  - `handle_retail` — filters on `type=retail`, migrates via the retail branch (`USD`), records invoice, and fans out.
  - `handle_wholesale` — filters on `type=wholesale`, migrates via the wholesale branch (`EUR`), records invoice with discount.
  - `handle_other` — declared with `converge=False`, receives raw unmodeled payloads into the audit log.
- `orders.legacy` & `orders.current` — fan-out destinations for retail orders, published at `1.0.0` and `3.0.0` respectively.
- `orders.requests` & `orders.replies` — request-reply flow negotiating response version via the inbound `accept-version` header.

## Tests

```bash
uv run pytest showcases/faststream
```
