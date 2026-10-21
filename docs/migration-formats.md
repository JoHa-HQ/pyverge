# Migration Formats

Choose the simplest format that expresses the edge.

| Format | Use when | Context |
| --- | --- | --- |
| RFC 6902 JSON Patch | structural add/remove/replace | no |
| JSONata | declarative expressions and runtime values | yes (planned) |
| Python callable | imperative logic or context access | yes |

## JSON Patch

```python
JsonPatchMigration(
    {
        "from": "1.0.0",
        "to": "2.0.0",
        "ops": [{"op": "add", "path": "/age", "value": None}],
    }
)
```

Portable and serializable. RFC 6902 has no variables, so JSON Patch stays
context-free by design.

## JSONata

Declarative expressions for formatting, arithmetic, filtering, and context
variables such as `$tenant_id`. Planned follow-up; until it lands, use a
callable for these cases.

## Python callable

```python
def migrate(data, context=None):
    data["tenant_id"] = context["tenant_id"]
    return data
```

Use for business logic that JSON Patch cannot express. Callables are the escape
hatch, not portable configuration.

See [Migrations](migration.md) for full op syntax, authoring rules, and
reconstruction.
