from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Generic

import pendulum
from semver import Version

from pyverge.core.types import VersionValue
from pyverge.core.versioning import ContentHasher

from .backend import GraphBackend
from .errors import VersionStrategyMismatchError

VERSION_STRATEGY_SEMVER = "semver"
VERSION_STRATEGY_DATE = "date"
VERSION_STRATEGY_NONE = "none"


def _strategy_name(value_type: type[object]) -> str:
    if issubclass(value_type, Version):
        return VERSION_STRATEGY_SEMVER
    if value_type is pendulum.Date:
        return VERSION_STRATEGY_DATE
    return f"{value_type.__module__}.{value_type.__qualname__}"


def version_strategy(values: Iterable[VersionValue]) -> str:
    """Return the graph-wide version strategy for parsed values."""
    types = {type(value) for value in values}
    if not types:
        return VERSION_STRATEGY_NONE
    names = tuple(_strategy_name(value_type) for value_type in types)
    if len(types) > 1:
        raise VersionStrategyMismatchError(names)
    return names[0]


@dataclass(frozen=True, slots=True)
class Revision:
    """Manifest-wide identity of one locked graph."""

    version_strategy: str
    versions: Mapping[str, tuple[str, ...]]
    content_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "versions",
            MappingProxyType(
                {kind: tuple(values) for kind, values in self.versions.items()}
            ),
        )

    def same_content(self, other: Revision) -> bool:
        return self.content_digest == other.content_digest

    def same_manifest(self, other: Revision) -> bool:
        return self == other

    def to_canonical(self) -> dict[str, object]:
        return {
            "version_strategy": self.version_strategy,
            "versions": {
                kind: list(values) for kind, values in sorted(self.versions.items())
            },
            "content_digest": self.content_digest,
        }

    def __hash__(self) -> int:
        return hash(
            (
                self.version_strategy,
                tuple(sorted(self.versions.items())),
                self.content_digest,
            )
        )


def content_digest(
    backend: GraphBackend,
    *,
    hasher: ContentHasher,
) -> str:
    """Hash graph content without revision metadata."""
    return hasher.digest(
        {
            "namespace": backend.namespace,
            "nodes": [
                (
                    node.id.digest(hasher),
                    backend.node_digests[node.id],
                )
                for node in backend.nodes
            ],
            "edges": [
                (
                    edge.id.digest(hasher),
                    backend.edge_digests[edge.id],
                    edge.id in backend.executable_edge_ids,
                )
                for edge in backend.edges
            ],
            "hooks": [
                (
                    edge_id.digest(hasher),
                    tuple(ref.digest(hasher) for ref in refs),
                )
                for edge_id, refs in backend.hook_specs.items()
            ],
        }
    )


def manifest_digest(
    backend: GraphBackend,
    revision: Revision,
    *,
    hasher: ContentHasher,
) -> str:
    """Hash the complete locked manifest, including its revision."""
    return hasher.digest(
        {
            "namespace": backend.namespace,
            "revision": revision.to_canonical(),
        }
    )


@dataclass(frozen=True, slots=True)
class VersionVectorRevisionPolicy(Generic[VersionValue]):
    """Derive a manifest revision from the backend's frozen version vector."""

    def derive(
        self,
        backend: GraphBackend[VersionValue],
        *,
        hasher: ContentHasher,
    ) -> Revision:
        values = [node.version for node in backend.nodes]
        versions = {
            kind: tuple(str(node.version) for node in backend.nodes_for_kind(kind))
            for kind in backend.nodes_by_kind
        }
        return Revision(
            version_strategy=version_strategy(values),
            versions=versions,
            content_digest=content_digest(backend, hasher=hasher),
        )


__all__ = [
    "VERSION_STRATEGY_DATE",
    "VERSION_STRATEGY_NONE",
    "VERSION_STRATEGY_SEMVER",
    "Revision",
    "VersionVectorRevisionPolicy",
    "content_digest",
    "manifest_digest",
    "version_strategy",
]
