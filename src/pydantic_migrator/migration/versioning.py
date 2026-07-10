"""Model version: supports semver and calendar date versioning.

Semver: ``1.0.0``, ``2.1.0-beta``, ``0.1.1.dev7``
Date:   ``2024-06-01``, ``2025-03-15``
"""

from __future__ import annotations

import logging
from functools import total_ordering
from typing import Generic, Self, get_args, get_origin

import pendulum
from semver import Version as SemVer

from .types import VersionValue, VModel

logger = logging.getLogger(__name__)


@total_ordering
class ModelVersion(Generic[VersionValue]):
    """A model version that can be either semver or ISO date.

    Optionally carries the Pydantic model class so the registry can
    treat ``(version, model)`` as a single comparable unit.
    """

    def __init__(
        self,
        value: VersionValue,
        model_cls: type[VModel],
    ) -> None:
        self._value: VersionValue = value
        self._model_cls: type[VModel] = model_cls

    @classmethod
    def parse(cls, value: VersionValue, model_cls: type[VModel]) -> Self:
        """Parse a string or pass through an existing ModelVersion."""
        try:
            return cls[SemVer](value=SemVer.parse(value), model_cls=model_cls)
        except ValueError:
            logger.debug(f"Failed to parse semver: {value!r}")

        try:
            parsed = pendulum.parse(value, exact=True)
            if isinstance(parsed, pendulum.DateTime):
                parsed = parsed.date()
            if not isinstance(parsed, pendulum.Date):
                raise ValueError(f"Expected date, got {parsed!r}")
            return cls[pendulum.Date](
                value=parsed,
                model_cls=model_cls,
            )
        except ValueError:
            logger.debug(f"Failed to parse date: {value!r}")

        msg = (
            f"Cannot parse version {value!r}. "
            "Expected semver (e.g. '1.0.0') or ISO date (e.g. '2024-06-01')."
        )
        raise ValueError(msg)

    @property
    def strategy(self) -> type[VersionValue]:
        return get_args(self.__orig_class__)[-1]

    @property
    def model_cls(self) -> type[VModel]:
        return self._model_cls

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, ModelVersion):
            return NotImplemented
        return self._value < other._value  # type: ignore[operator]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ModelVersion):
            return NotImplemented
        if self.strategy != other.strategy:
            raise TypeError(
                f"Cannot compare ModelVersion[{self.strategy}] with ModelVersion[{other.strategy}]"  # noqa: E501
            )
        return self._value == other._value

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, ModelVersion):
            return NotImplemented
        return self._value > other._value  # type: ignore[operator]

    def __hash__(self) -> int:
        return hash(self._value)

    def __str__(self) -> str:
        return str(self._value)

    def __repr__(self) -> str:
        return f"ModelVersion[{self.strategy.__name__}]({self._value})"
