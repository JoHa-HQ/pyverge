# Migration Formats

Choose the simplest format that expresses the edge.

| Format | Use when | Context |
| --- | --- | --- |
| RFC 6902 JSON Patch | structural add/remove/replace | no |
| JSONata | declarative expressions and runtime values | yes |
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
variables such as `$tenant_id`.

```python
@manager.migration("User", "1.0.0", "2.0.0", strategy="jsonata")
class UserV1ToV2:
    expression = """
    {
      "kind": kind,
      "version": "2.0.0",
      "full_name": first_name & " " & last_name,
      "email": $lowercase(email),
      "tenant_id": $tenant_id
    }
    """
```

```python
result = manager.migrate(payload, context={"tenant_id": "tenant_99"})
```

A JSONata expression replaces the payload rather than patching it. Emit every
target field, including `kind`; the engine stamps the target `version`.
Expressions compile at registration and invalid syntax raises `ValueError`.

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
