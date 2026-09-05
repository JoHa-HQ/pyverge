# Target Policy

A target policy answers one question for every discovered entry: *"what version
should this entry converge to?"* The policy is compiled into a lightweight
`TargetResolver` before the engine sees it.

```mermaid
flowchart TD
    subgraph Declarative forms
        A[None / skip]
        B[latest / earliest]
        C[explicit version string]
        D[model class or Versionable]
        E[per-kind mapping with wildcard]
    end

    Declarative forms -->|compile| R[TargetResolver]
    R -->|per entry| T[Target version]
    T --> Engine
```

| Form | Meaning |
| ---- | ------- |
| `None` or `"skip"` | Leave every entry unchanged. |
| `"latest"` / `"earliest"` | Converge to the registry extreme for the entry's kind. |
| version string (e.g. `"1.5.0"`) | Converge to the registered version matching the entry's kind. |
| model class or `Versionable` | Converge to the exact registered version represented by that class or node. |
| `dict` | Per-kind overrides; `"*"` is the fallback for any unlisted kind. |
| callable `TargetResolver` | External decision system; returned as-is. |

Per-kind mappings are useful when different model families in the same payload
need different convergence rules:

```python
manager.migrate(
    data,
    target={
        "LegacySensor": "1.5.0",  # pin legacy data explicitly
        "*": "latest",             # everything else moves forward
    },
)
```
