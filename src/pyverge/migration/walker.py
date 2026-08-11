"""Schema-aware payload discovery walkers."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Generic

from pydantic import BaseModel

from .exceptions import DiscoveryValidationError, MaxDepthExceededError
from .models import DiscoverySettings
from .registry import Registry
from .types import (
    Entry,
    MigrationDirectionStrategy,
    ModelAdapter,
    ModelBase,
    TargetResolver,
    VersionValue,
)
from .types import (
    Walker as WalkerProtocol,
)
from .versioning import SentinelNode


class CompoundKeyWalker(WalkerProtocol, Generic[VersionValue]):
    """Containerless walker: every dict is checked for ``(kind, version)``.

    Only registered compound keys produce entries.  No structural validation
    is performed beyond the presence of the version marker.
    """

    def __init__(
        self,
        registry: Registry[VersionValue, ModelBase],
        *,
        settings: DiscoverySettings,
        adapter: ModelAdapter,
        direction: MigrationDirectionStrategy = "any",
    ) -> None:
        self._registry = registry
        self._settings = settings
        self._adapter = adapter
        self._direction = direction

    @property
    def registry(self) -> Registry[VersionValue, ModelBase]:
        """The registry this walker discovers against."""
        return self._registry

    def discover(
        self,
        data: dict[str, Any],
        *,
        container: type[Any] | None = None,
        target_resolver: TargetResolver,
        max_depth: int = -1,
    ) -> Iterator[Entry]:
        kp = self._settings.kind_property
        vp = self._settings.version_property
        yield from self._walk(data, (), 0, 0, kp, vp, max_depth, target_resolver)

    def _walk(
        self,
        value: Any,
        path: tuple[str | int, ...],
        depth: int,
        versioned_depth: int,
        kp: str,
        vp: str,
        max_depth: int,
        target_resolver: TargetResolver,
    ) -> Iterator[Entry]:
        if isinstance(value, dict):
            kind = value.get(kp)
            version_str = value.get(vp)
            is_versioned = False
            if isinstance(kind, str) and isinstance(version_str, str):
                try:
                    sentinel = SentinelNode(kind, self._adapter.of(version_str))
                except Exception:
                    sentinel = None
                if sentinel is not None and self._registry.has_model(sentinel):
                    is_versioned = True
                    if max_depth >= 0 and versioned_depth > max_depth:
                        raise MaxDepthExceededError(
                            path=path,
                            depth=depth,
                            kind=kind,
                            version=version_str,
                            max_depth=max_depth,
                        )
                    try:
                        source = self._registry.get_model(sentinel)
                    except Exception:
                        pass
                    else:
                        target = target_resolver(source)
                        if target is not None and (
                            self._direction == "any"
                            or (self._direction == "forward" and source < target)
                            or (self._direction == "backward" and source > target)
                        ):
                            yield (path, depth, source)

            child_versioned_depth = (
                versioned_depth + 1 if is_versioned else versioned_depth
            )
            for key, nested in value.items():
                yield from self._walk(
                    nested,
                    (*path, key),
                    depth + 1,
                    child_versioned_depth,
                    kp,
                    vp,
                    max_depth,
                    target_resolver,
                )

        elif isinstance(value, list):
            for idx, item in enumerate(value):
                yield from self._walk(
                    item,
                    (*path, idx),
                    depth + 1,
                    versioned_depth,
                    kp,
                    vp,
                    max_depth,
                    target_resolver,
                )


class PydanticWalker(WalkerProtocol, Generic[VersionValue]):
    """Container-driven walker that uses a Pydantic model to guide discovery.

    Validates the payload against *container* first, then recursively visits
    fields whose annotations carry ``BaseModel`` subclasses.  Versioned entries
    are extracted from validated sub-dicts.
    """

    def __init__(
        self,
        registry: Registry[VersionValue, ModelBase],
        *,
        settings: DiscoverySettings,
        adapter: ModelAdapter,
    ) -> None:
        self._registry = registry
        self._settings = settings
        self._adapter = adapter

    @property
    def registry(self) -> Registry[VersionValue, ModelBase]:
        """The registry this walker discovers against."""
        return self._registry

    def discover(
        self,
        data: dict[str, Any],
        *,
        container: type[Any] | None = None,
        target_resolver: TargetResolver,
        max_depth: int = -1,
    ) -> Iterator[Entry]:
        if container is None or not issubclass(container, BaseModel):
            raise DiscoveryValidationError(
                path=(),
                message="PydanticWalker requires a container model",
            )

        validation_mode = self._settings.validation_mode
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
                raise DiscoveryValidationError(
                    path=(),
                    message=f"Payload failed container validation: {exc}",
                ) from exc

        kp = self._settings.kind_property
        vp = self._settings.version_property
        yield from self._walk(
            validated,
            (),
            0,
            container,
            kp,
            vp,
            max_depth,
            target_resolver,
        )

    def _walk(
        self,
        value: Any,
        path: tuple[str | int, ...],
        depth: int,
        parent_model: type[BaseModel] | None,
        kp: str,
        vp: str,
        max_depth: int,
        target_resolver: TargetResolver,
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
            kind = value.get(kp)
            version_str = value.get(vp)
            if isinstance(kind, str) and isinstance(version_str, str):
                try:
                    sentinel = SentinelNode(kind, self._adapter.of(version_str))
                except Exception:
                    sentinel = None
                if sentinel is not None and self._registry.has_model(sentinel):
                    try:
                        source = self._registry.get_model(sentinel)
                    except Exception:
                        pass
                    else:
                        target = target_resolver(source)
                        if target is not None:
                            yield (path, depth, source)
                            # Do not recurse into already-discovered entries
                            return

            field_model: type[BaseModel] | None = None
            if parent_model is not None and path:
                field_model = self._adapter.field_model(parent_model, str(path[-1]))

            for key, nested in value.items():
                child_model = field_model
                if child_model is not None:
                    resolved = self._adapter.field_model(child_model, str(key))
                    if resolved is not None:
                        child_model = resolved

                yield from self._walk(
                    nested,
                    (*path, key),
                    depth + 1,
                    child_model,
                    kp,
                    vp,
                    max_depth,
                    target_resolver,
                )

        elif isinstance(value, list):
            item_model: type[BaseModel] | None = None
            if parent_model is not None and path:
                item_model = self._adapter.field_model(parent_model, str(path[-1]))

            for idx, item in enumerate(value):
                yield from self._walk(
                    item,
                    (*path, idx),
                    depth + 1,
                    item_model,
                    kp,
                    vp,
                    max_depth,
                    target_resolver,
                )
