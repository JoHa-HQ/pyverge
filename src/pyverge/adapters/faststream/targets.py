"""FastStream target selectors: headers, topics, and defaults.

Transport logic lives with the FastStream adapter. A selector returns ``None``
when it does not apply; ``FirstMatch`` composes selectors in precedence order.
"""

from __future__ import annotations

from pyverge.manager.types import TargetPolicy

from .types import (
    HeaderParser,
    MessageHeaders,
    TargetContext,
    TargetSelector,
    TopicTargets,
)

DEFAULT_TARGET = "latest"
DEFAULT_VERSION_HEADER = "accept-version"


class HeaderTarget:
    """Select the target from a message header, when present."""

    def __init__(self, header: str = DEFAULT_VERSION_HEADER) -> None:
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


class DefaultTarget:
    """Always select the fallback target."""

    def __init__(self, target: TargetPolicy = DEFAULT_TARGET) -> None:
        self._target = target

    def select(self, context: TargetContext) -> TargetPolicy | None:
        return self._target


class FirstMatch:
    """Return the first non-``None`` selection from the configured selectors."""

    def __init__(self, *selectors: TargetSelector) -> None:
        self._selectors = selectors

    @classmethod
    def for_topics(
        cls,
        topics: tuple[str, ...],
        targets: TargetPolicy | TopicTargets,
        header: str | None = None,
    ) -> FirstMatch:
        """Build the standard chain: header -> topic -> latest."""
        head = (HeaderTarget(header),) if header is not None else ()
        return cls(
            *head,
            TopicTarget(TopicTargets.coerce(targets, topics)),
            DefaultTarget(),
        )

    def select(self, context: TargetContext) -> TargetPolicy | None:
        for selector in self._selectors:
            target = selector.select(context)
            if target is not None:
                return target
        return None


__all__ = [
    "DEFAULT_TARGET",
    "DEFAULT_VERSION_HEADER",
    "DefaultTarget",
    "FirstMatch",
    "HeaderTarget",
    "TopicTarget",
]
