from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Generic, Literal

from pyverge.core.errors import MaxDepthExceededError, PayloadValidationError
from pyverge.core.types import VersionValue
from pyverge.execution.types import (
    Entry,
)
from pyverge.registry import (
    Registry,
)
from pyverge.schemas.types import (
    ModelAdapter,
)
from pyverge.versioning import (
    VersionKey,
    VersionNode,
)


class CompositeExtractor(Generic[VersionValue]):
    """One container-aware walker for both discovery modes.

    - ``container is None``: dict scanning — every dict is checked for a
      registered ``(kind, version)`` pair (containerless semantics).
    - ``container`` the adapter can handle: the payload is validated against
      the container and descent follows the container's field models
      (container-guided semantics).
    - ``container`` the adapter cannot handle: fail fast with
      :class:`PayloadValidationError` before any migration runs.
    """

    def __init__(
        self,
        registry: Registry[VersionValue],
        *,
        adapter: ModelAdapter,
        validation_mode: Literal["strict", "lax", "none"] = "lax",
    ) -> None:
        self._registry = registry
        self._validation_mode = validation_mode
        self._adapter = adapter

    @property
    def registry(self) -> Registry[VersionValue]:
        return self._registry

    def extract(
        self,
        data: dict[str, Any],
        *,
        container: type[Any] | None = None,
        max_depth: int = -1,
    ) -> Iterator[Entry]:
        kp = self._adapter.kind_property
        vp = self._adapter.version_property

        if container is None:
            yield from self._walk_containerless(data, (), 0, 0, kp, vp, max_depth)
            return

        if not self._adapter.can_handle(container):
            raise PayloadValidationError(
                path=(),
                message="container is not a recognized model type",
            )

        validation_mode = self._validation_mode
        if validation_mode == "none":
            validated = data
        else:
            try:
                validated = self._adapter.validate(
                    data,
                    container,
                    strict=(validation_mode == "strict"),
                )
            except Exception as exc:
                raise PayloadValidationError(
                    path=(),
                    message=f"Payload failed container validation: {exc}",
                ) from exc

        yield from self._walk_guided(validated, (), 0, container, kp, vp, max_depth)

    def _match(
        self,
        value: Any,
        kp: str,
        vp: str,
    ) -> VersionNode[VersionValue] | None:
        if not isinstance(value, dict):
            return None
        kind = value.get(kp)
        version_str = value.get(vp)
        if not (isinstance(kind, str) and isinstance(version_str, str)):
            return None
        try:
            key = VersionKey[VersionValue](
                _value=self._adapter.of(version_str), _kind=kind
            )
        except Exception:
            return None
        if not self._registry.has_model(key):
            return None
        try:
            return self._registry.get_model(key)
        except Exception:
            return None

    def _walk_containerless(
        self,
        value: Any,
        path: tuple[str | int, ...],
        depth: int,
        versioned_depth: int,
        kp: str,
        vp: str,
        max_depth: int,
    ) -> Iterator[Entry]:
        is_versioned = False
        if isinstance(value, dict):
            source = self._match(value, kp, vp)
            if source is not None:
                is_versioned = True
                if max_depth >= 0 and versioned_depth > max_depth:
                    raise MaxDepthExceededError(
                        path=path,
                        depth=depth,
                        kind=source.kind,
                        version=str(source.version[1]),
                        max_depth=max_depth,
                    )
                yield (path, depth, source)

            child_versioned_depth = (
                versioned_depth + 1 if is_versioned else versioned_depth
            )
            for key, nested in value.items():
                yield from self._walk_containerless(
                    nested,
                    (*path, key),
                    depth + 1,
                    child_versioned_depth,
                    kp,
                    vp,
                    max_depth,
                )
        elif isinstance(value, list):
            for idx, item in enumerate(value):
                yield from self._walk_containerless(
                    item,
                    (*path, idx),
                    depth + 1,
                    versioned_depth,
                    kp,
                    vp,
                    max_depth,
                )

    def _walk_guided(
        self,
        value: Any,
        path: tuple[str | int, ...],
        depth: int,
        parent_model: type[Any] | None,
        kp: str,
        vp: str,
        max_depth: int,
    ) -> Iterator[Entry]:
        if max_depth >= 0 and depth > max_depth:
            kind = value.get(kp, "") if isinstance(value, dict) else ""
            version = value.get(vp, "") if isinstance(value, dict) else ""
            raise MaxDepthExceededError(
                path=path,
                depth=depth,
                kind=str(kind),
                version=str(version),
                max_depth=max_depth,
            )

        if isinstance(value, dict):
            source = self._match(value, kp, vp)
            if source is not None:
                yield (path, depth, source)
                # Do not recurse into already-discovered entries
                return

            field_model: type[Any] | None = None
            if parent_model is not None and path:
                field_model = self._adapter.field_model(parent_model, str(path[-1]))

            for key, nested in value.items():
                child_model = field_model
                if child_model is not None:
                    resolved = self._adapter.field_model(child_model, str(key))
                    if resolved is not None:
                        child_model = resolved

                yield from self._walk_guided(
                    nested,
                    (*path, key),
                    depth + 1,
                    child_model,
                    kp,
                    vp,
                    max_depth,
                )

        elif isinstance(value, list):
            item_model: type[Any] | None = None
            if parent_model is not None and path:
                item_model = self._adapter.field_model(parent_model, str(path[-1]))

            for idx, item in enumerate(value):
                yield from self._walk_guided(
                    item,
                    (*path, idx),
                    depth + 1,
                    item_model,
                    kp,
                    vp,
                    max_depth,
                )


class SchemaFieldsExtractor(CompositeExtractor[VersionValue]):
    """Extract versioned dicts by scanning schema fields in the payload."""

    def extract(
        self,
        data: dict[str, Any],
        *,
        container: type[Any] | None = None,
        max_depth: int = -1,
    ) -> Iterator[Entry]:
        if container is not None:
            raise ValueError("SchemaFieldsExtractor does not accept a container")
        kp = self._adapter.kind_property
        vp = self._adapter.version_property
        yield from self._walk_containerless(data, (), 0, 0, kp, vp, max_depth)


class ContainerExtractor(CompositeExtractor[VersionValue]):
    """Extract entries by following a typed container's field models."""

    def extract(
        self,
        data: dict[str, Any],
        *,
        container: type[Any] | None = None,
        max_depth: int = -1,
    ) -> Iterator[Entry]:
        if container is None:
            raise ValueError("ContainerExtractor requires a container")
        if not self._adapter.can_handle(container):
            raise PayloadValidationError(
                path=(),
                message="container is not a recognized model type",
            )
        validation_mode = self._validation_mode
        if validation_mode == "none":
            validated = data
        else:
            try:
                validated = self._adapter.validate(
                    data,
                    container,
                    strict=(validation_mode == "strict"),
                )
            except Exception as exc:
                raise PayloadValidationError(
                    path=(),
                    message=f"Payload failed container validation: {exc}",
                ) from exc
        kp = self._adapter.kind_property
        vp = self._adapter.version_property
        yield from self._walk_guided(validated, (), 0, container, kp, vp, max_depth)


__all__ = ["CompositeExtractor", "ContainerExtractor", "SchemaFieldsExtractor"]
