"""Declarative JSONata migrations."""

from __future__ import annotations

from threading import Lock
from typing import Any

from jsonata import Jsonata

from pyverge.core.context import EMPTY_CONTEXT, MigrationContext
from pyverge.core.types import ModelData


class JsonataMigration:
    """Compile a JSONata expression into a migration callable.

    The expression produces the whole migrated payload. Runtime context values
    are exposed as JSONata variables (``$tenant_id`` etc.).
    """

    def __init__(self, spec: str | dict[str, Any]) -> None:
        if isinstance(spec, str):
            expression = spec
            self.spec: dict[str, Any] = {"expression": expression}
        elif isinstance(spec, dict):
            for key in ("from", "to"):
                if not isinstance(spec.get(key), str) or not spec[key]:
                    raise ValueError(
                        f"Migration spec requires a non-empty '{key}' version string"
                    )
            expression = spec.get("expression")
            if not isinstance(expression, str) or not expression.strip():
                raise ValueError(
                    "Migration spec requires a non-empty 'expression' string"
                )
            self.spec = dict(spec)
        else:
            raise ValueError("Migration spec must be a JSONata string or object")

        if not expression.strip():
            raise ValueError("JSONata expression must be a non-empty string")

        self.expression = expression
        try:
            self._compiled = Jsonata(expression)
        except Exception as exc:
            raise ValueError(f"Invalid JSONata expression: {exc}") from exc
        self._lock = Lock()

    def __call__(
        self,
        data: ModelData,
        context: MigrationContext | None = None,
    ) -> ModelData:
        """Evaluate the expression against *data* and runtime context."""
        active = context if context is not None else EMPTY_CONTEXT
        bindings = dict(active)
        with self._lock:
            result = self._compiled.evaluate(data, bindings=bindings or None)
        if not isinstance(result, dict):
            raise TypeError(
                "JSONata migration must return a JSON object, "
                f"got {type(result).__name__}"
            )
        return result

    def __repr__(self) -> str:
        return f"JsonataMigration({self.expression!r})"
