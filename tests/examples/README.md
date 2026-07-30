# Test Examples

This directory contains Pydantic example models used by the test suite. The
examples are organized by provider; additional model providers can mirror the
``pydantic/`` layout.

## Layout

```
tests/examples/
├── pydantic/
│   ├── base.py              # Provider-specific BaseModel and family bases
│   ├── semver.py            # Semver-versioned User models
│   ├── chrono.py            # Date-versioned User models
│   ├── semver_nested.py     # Nested semver models (Person/Address/Contact)
│   └── chrono_nested.py     # Nested date-versioned models
└── README.md
```

## Design

- Each model family inherits from a shared base in ``base.py`` that provides the
  ``kind`` field with a default value.
- Each concrete version class declares its ``version`` as a ``Literal`` with a
  matching default, following the idiomatic Pydantic pattern:
  ``version: Literal["1.0.0"] = "1.0.0"``.
- Container models wrap discriminated unions and are used by the
  ``PydanticWalker`` during discovery.

Higher-level registration patterns (lazy registration and coordination across
multiple model families) are documented in the user documentation under
``docs/``.
