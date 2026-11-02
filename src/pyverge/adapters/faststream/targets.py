"""Target selection and negotiated-header parsing."""

from __future__ import annotations

import json
from functools import singledispatchmethod
from typing import Any, cast

from pyverge.graph.planning.targets import DefaultTarget
from pyverge.graph.planning.targets import FirstMatch as _FirstMatch
from pyverge.manager.types import TargetPolicy, VersionRange

from .domain import (
    MessageHeaders,
    NegotiationError,
    TargetContext,
    TopicTargets,
)


class HeaderParser:
    """Parse a negotiated target header.

    Scalar values are target policies; JSON objects are per-kind mappings or
    bounded version ranges.
    """

    @singledispatchmethod
    def parse(self, value: Any) -> TargetPolicy:
        raise NegotiationError("version header must be a string")

    @parse.register
    def _(self, value: bytes) -> TargetPolicy:
        return self.parse(value.decode())

    @parse.register
    def _(self, value: str) -> TargetPolicy:
        raw = value.strip()
        if not raw:
            raise NegotiationError("version header must be a non-empty string")
        if raw.startswith("{"):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise NegotiationError(f"invalid version header JSON: {exc}") from exc
            return self._mapping(parsed)
        return raw

    @singledispatchmethod
    def _mapping(self, value: Any) -> TargetPolicy:
        raise NegotiationError(
            "version header mapping must contain string keys and values"
        )

    @_mapping.register
    def _(self, value: dict) -> TargetPolicy:
        if value and set(value) <= {"gte", "lt", "eq"}:
            if not all(isinstance(item, str) for item in value.values()):
                raise NegotiationError("version header range bounds must be strings")
            return VersionRange(
                gte=value.get("gte"),
                lt=value.get("lt"),
                eq=value.get("eq"),
            )
        if not all(
            isinstance(key, str) and isinstance(item, str)
            for key, item in value.items()
        ):
            raise NegotiationError(
                "version header mapping must contain string keys and values"
            )
        return cast("TargetPolicy", value)


class HeaderTarget:
    """Select the target from a message header, when present."""

    def __init__(self, header: str) -> None:
        self._header = header
        self._parser = HeaderParser()

    def select(self, context: TargetContext) -> TargetPolicy | None:
        value = MessageHeaders(context.headers).get(self._header)
        if value is None:
            return None
        return self._parser.parse(value)


class TopicTarget:
    """Select a target configured for the message topic."""

    def __init__(self, targets: TopicTargets) -> None:
        self._targets = targets

    def select(self, context: TargetContext) -> TargetPolicy | None:
        return self._targets.get(context.topic)


class FirstMatch(_FirstMatch[TargetContext]):
    """FastStream selector chain with topic-aware construction."""

    @classmethod
    def for_topics(
        cls,
        topics: tuple[str, ...],
        targets: TargetPolicy | TopicTargets,
        *,
        default_target: TargetPolicy,
        header: str | None = None,
    ) -> FirstMatch:
        head = (HeaderTarget(header),) if header is not None else ()
        return cls(
            *head,
            TopicTarget(TopicTargets.coerce(targets, topics)),
            DefaultTarget(default_target),
        )


__all__ = [
    "DefaultTarget",
    "FirstMatch",
    "HeaderParser",
    "HeaderTarget",
    "TopicTarget",
]
