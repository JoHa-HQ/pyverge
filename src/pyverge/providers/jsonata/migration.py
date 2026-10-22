from __future__ import annotations

from collections.abc import Mapping
from functools import singledispatchmethod
from threading import Lock
from typing import Any, Self

from jsonata import Jsonata

from pyverge.core.context import EMPTY_CONTEXT, MigrationContext
from pyverge.core.types import ModelData


class JsonataTransform:
    """Callable migration compiled from a JSONata expression."""

    def __init__(self, expression: str) -> None:
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
        return f"JsonataTransform({self.expression!r})"


class JsonataMigration:
    """Declarative JSONata spec that produces a callable migration."""

    def __init__(
        self,
        expression: str,
        *,
        spec: Mapping[str, Any] | None = None,
    ) -> None:
        self.expression = expression
        self.spec: dict[str, Any] = (
            dict(spec) if spec is not None else {"expression": expression}
        )
        self._migration = JsonataTransform(expression)

    @classmethod
    def from_expression(cls, expression: str) -> Self:
        """Build from a bare JSONata expression string."""
        if not isinstance(expression, str):
            raise TypeError("JSONata expression must be a string")
        return cls(expression)

    @classmethod
    def from_spec(cls, spec: Mapping[str, Any]) -> Self:
        """Build from a declarative migration spec."""
        for key in ("from", "to"):
            if not isinstance(spec.get(key), str) or not spec[key]:
                raise ValueError(
                    f"Migration spec requires a non-empty '{key}' version string"
                )
        expression = spec.get("expression")
        if not isinstance(expression, str) or not expression.strip():
            raise ValueError("Migration spec requires a non-empty 'expression' string")
        return cls(expression, spec=spec)

    @singledispatchmethod
    @classmethod
    def create(cls, value: str | Mapping[str, Any]) -> Self:
        """Build from a string or mapping."""
        raise TypeError(f"Unsupported JSONata migration input: {type(value).__name__}")

    @create.register(str)
    @classmethod
    def _(cls, expression: str) -> Self:
        return cls.from_expression(expression)

    @create.register(Mapping)
    @classmethod
    def _(cls, spec: Mapping[str, Any]) -> Self:
        return cls.from_spec(spec)

    @property
    def migration(self) -> JsonataTransform:
        """The executable migration callable."""
        return self._migration
