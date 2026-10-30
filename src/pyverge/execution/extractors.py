from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, replace
from typing import Any, Generic, Literal

from pyverge.core.errors import MaxDepthExceededError, PayloadValidationError
from pyverge.core.types import VersionValue
from pyverge.execution.types import (
    Entry,
)
from pyverge.graph.types import GraphView
from pyverge.schemas.types import (
    ModelAdapter,
)
from pyverge.versioning import (
    VersionKey,
    VersionNode,
)


@dataclass(frozen=True, slots=True)
class _WalkContext:
    kp: str
    vp: str
    max_depth: int
    versioned_depth: int = 0
    parent_model: type[Any] | None = None


class PayloadWalker(Generic[VersionValue]):
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
        graph: GraphView[VersionValue],
        *,
        adapter: ModelAdapter,
        validation_mode: Literal["strict", "lax", "none"] = "lax",
    ) -> None:
        self._graph = graph
        self._validation_mode = validation_mode
        self._adapter = adapter

    @property
    def graph(self) -> GraphView[VersionValue]:
        return self._graph

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
            yield from self._walk_containerless(
                data,
                (),
                0,
                _WalkContext(kp, vp, max_depth),
            )
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

        yield from self._walk_guided(
            validated,
            (),
            0,
            _WalkContext(kp, vp, max_depth, parent_model=container),
        )

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
                namespace=self._graph.namespace,
                kind=kind,
                version=version_str,
            )
        except Exception:
            return None
        if not self._graph.has_model(key):
            return None
        try:
            return self._graph.get_model(key)
        except Exception:
            return None

    def _walk_containerless(
        self,
        value: Any,
        path: tuple[str | int, ...],
        depth: int,
        ctx: _WalkContext,
    ) -> Iterator[Entry]:
        if isinstance(value, dict):
            source = self._match(value, ctx.kp, ctx.vp)
            if source is not None:
                if ctx.max_depth >= 0 and ctx.versioned_depth > ctx.max_depth:
                    raise MaxDepthExceededError(
                        path=path,
                        depth=depth,
                        kind=source.kind,
                        version=str(source.version),
                        max_depth=ctx.max_depth,
                    )
                yield (path, depth, source)
                ctx = replace(ctx, versioned_depth=ctx.versioned_depth + 1)
            for key, nested in value.items():
                yield from self._walk_containerless(
                    nested, (*path, key), depth + 1, ctx
                )
        elif isinstance(value, list):
            for idx, item in enumerate(value):
                yield from self._walk_containerless(item, (*path, idx), depth + 1, ctx)

    def _walk_guided(
        self,
        value: Any,
        path: tuple[str | int, ...],
        depth: int,
        ctx: _WalkContext,
    ) -> Iterator[Entry]:
        if ctx.max_depth >= 0 and depth > ctx.max_depth:
            kind = value.get(ctx.kp, "") if isinstance(value, dict) else ""
            version = value.get(ctx.vp, "") if isinstance(value, dict) else ""
            raise MaxDepthExceededError(
                path=path,
                depth=depth,
                kind=str(kind),
                version=str(version),
                max_depth=ctx.max_depth,
            )
        if isinstance(value, dict):
            yield from self._walk_guided_dict(value, path, depth, ctx)
        elif isinstance(value, list):
            yield from self._walk_guided_list(value, path, depth, ctx)

    def _walk_guided_dict(
        self,
        value: dict[str, Any],
        path: tuple[str | int, ...],
        depth: int,
        ctx: _WalkContext,
    ) -> Iterator[Entry]:
        source = self._match(value, ctx.kp, ctx.vp)
        if source is not None:
            yield (path, depth, source)
            return

        field_model: type[Any] | None = None
        if ctx.parent_model is not None and path:
            field_model = self._adapter.field_model(ctx.parent_model, str(path[-1]))

        for key, nested in value.items():
            child_model = field_model
            if child_model is not None:
                child_model = (
                    self._adapter.field_model(child_model, str(key)) or child_model
                )
            yield from self._walk_guided(
                nested,
                (*path, key),
                depth + 1,
                replace(ctx, parent_model=child_model),
            )

    def _walk_guided_list(
        self,
        value: list[Any],
        path: tuple[str | int, ...],
        depth: int,
        ctx: _WalkContext,
    ) -> Iterator[Entry]:
        item_model: type[Any] | None = None
        if ctx.parent_model is not None and path:
            item_model = self._adapter.field_model(ctx.parent_model, str(path[-1]))
        for idx, item in enumerate(value):
            yield from self._walk_guided(
                item,
                (*path, idx),
                depth + 1,
                replace(ctx, parent_model=item_model),
            )


class SchemaFieldsExtractor(PayloadWalker[VersionValue]):
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
        yield from self._walk_containerless(
            data,
            (),
            0,
            _WalkContext(kp, vp, max_depth),
        )


class ContainerExtractor(PayloadWalker[VersionValue]):
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
        yield from self._walk_guided(
            validated,
            (),
            0,
            _WalkContext(kp, vp, max_depth, parent_model=container),
        )


__all__ = ["ContainerExtractor", "PayloadWalker", "SchemaFieldsExtractor"]
