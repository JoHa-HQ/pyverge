"""Model version: supports semver and calendar date versioning.

Semver: ``1.0.0``, ``2.1.0-beta``, ``0.1.1.dev7``
Date:   ``2024-06-01``, ``2025-03-15``
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import total_ordering
from typing import Generic

import pendulum
from semver import Version

from .types import ModelKind, VersionValue, VModel

logger = logging.getLogger(__name__)


@total_ordering
@dataclass(frozen=True, slots=True)
class VersionedModel(Generic[VersionValue, VModel]):
    """A model version that can be either semver or ISO date.

    Optionally carries the Pydantic model class so the registry can
    treat ``(version, kind)`` as a single comparable unit.
    """

    _model: type[VModel]
    _value: VersionValue
    _kind: ModelKind

    @classmethod
    def of(cls, value: str) -> Version | pendulum.Date:
        """Parse a version string (mostly coming from Literal), then determine the strategy"""  # noqa: E501
        try:
            return Version.parse(value)
        except ValueError:
            logger.debug(f"Failed to parse semver: {str(value)!r}")

        try:
            parsed = pendulum.parse(str(value), exact=True)
            if isinstance(parsed, pendulum.DateTime):
                parsed = parsed.date()
            if not isinstance(parsed, pendulum.Date):
                raise ValueError(f"Expected date, got {parsed!r}")
            return parsed
        except ValueError:
            logger.debug(f"Failed to parse date: {value!r}")

        msg = (
            f"Cannot parse version {value!r}. "
            "Expected semver (e.g. '1.0.0') or ISO date (e.g. '2024-06-01')."
        )
        raise ValueError(msg)

    @property
    def strategy(self) -> type[VersionValue]:
        return type(self._value)

    @property
    def model(self) -> type[VModel]:
        return self._model

    @property
    def version(self) -> tuple[ModelKind, VersionValue]:
        return self._kind, self._value

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, (VersionedModel, VersionSentinel)):
            raise NotImplementedError(
                f"Cannot compare {self.__class__.__name__} with {other.__class__.__name__}"  # noqa: E501
            )
        elif self.strategy != other.strategy:
            raise TypeError(
                f"Cannot compare {self.strategy.__name__} with {other.strategy.__name__}"  # noqa: E501
            )
        return (self._kind, self._value) < (other._kind, other._value)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, (VersionedModel, VersionSentinel)):
            raise NotImplementedError(
                f"Cannot compare {self.__class__.__name__} with {other.__class__.__name__}"  # noqa: E501
            )
        elif self.strategy != other.strategy:
            raise TypeError(
                f"Cannot compare {self.strategy.__name__} with {other.strategy.__name__}"  # noqa: E501
            )
        return (self._kind, self._value) == (other._kind, other._value)

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, (VersionedModel, VersionSentinel)):
            raise NotImplementedError(
                f"Cannot compare {self.__class__.__name__} with {other.__class__.__name__}"  # noqa: E501
            )
        elif self.strategy != other.strategy:
            raise TypeError(
                f"Cannot compare {self.strategy.__name__} with {other.strategy.__name__}"  # noqa: E501
            )
        return (self._kind, self._value) > (other._kind, other._value)

    def __hash__(self) -> int:
        return hash((self._kind, self._value))

    def __str__(self) -> str:
        return f"{self._kind}:{self._value}"

    def __repr__(self) -> str:
        return f"ModelVersion[{self.strategy.__name__}, {self.model.__name__}]({self._value}, {self._kind})"  # noqa: E501


@total_ordering
@dataclass(frozen=True, slots=True)
class VersionSentinel(Generic[VersionValue]):
    """Lightweight value-only sentinel for bisect lookups.

    Carries no model binding — only the version value — so the registry
    can search by version string without constructing a full VersionedModel.
    """

    _kind: ModelKind
    _value: VersionValue

    @property
    def strategy(self) -> type[VersionValue]:
        return type(self._value)

    @property
    def kind(self) -> ModelKind:
        return self._kind

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, (VersionedModel, VersionSentinel)):
            raise NotImplementedError(
                f"Cannot compare {self.__class__.__name__} with {other.__class__.__name__}"  # noqa: E501
            )
        elif self.strategy != other.strategy:
            raise TypeError(
                f"Cannot compare {self.strategy.__name__} with {other.strategy.__name__}"  # noqa: E501
            )
        return (self._kind, self._value) < (other._kind, other._value)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, (VersionedModel, VersionSentinel)):
            raise NotImplementedError(
                f"Cannot compare {self.__class__.__name__} with {other.__class__.__name__}"  # noqa: E501
            )
        elif self.strategy != other.strategy:
            raise TypeError(
                f"Cannot compare {self.strategy.__name__} with {other.strategy.__name__}"  # noqa: E501
            )
        return (self._kind, self._value) == (other._kind, other._value)

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, (VersionedModel, VersionSentinel)):
            raise NotImplementedError(
                f"Cannot compare {self.__class__.__name__} with {other.__class__.__name__}"  # noqa: E501
            )
        elif self.strategy != other.strategy:
            raise TypeError(
                f"Cannot compare {self.strategy.__name__} with {other.strategy.__name__}"  # noqa: E501
            )
        return (self._kind, self._value) > (other._kind, other._value)

    def __hash__(self) -> int:
        return hash((self._kind, self._value))

    def __str__(self) -> str:
        return f"{self._kind}:{self._value}"
