"""Schema-aware payload discovery walkers."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel

from .exceptions import DiscoveryValidationError, MaxDepthExceededError
from .models import DiscoverySettings
from .registry import Registry
from .types import (
    Entry,
    MigrationDirectionStrategy,
    TargetResolver,
    VersionValue,
)
from .types import (
    Walker as WalkerProtocol,
)
from .versioning import SentinelNode, VersionNode


def _resolve_base_model(annotation: Any) -> type[BaseModel] | None:
    """Return the first concrete ``BaseModel`` subclass inside *annotation*.

    Handles direct types, ``Optional[T]``, ``list[T]``, and ``Union`` forms.
    """
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation

    origin = getattr(annotation, "__origin__", None)
    args = getattr(annotation, "__args__", ())

    if origin is list and args:
        return _resolve_base_model(args[0])

    for arg in args:
        resolved = _resolve_base_model(arg)
        if resolved is not None:
            return resolved

    return None


def _version_value(registry: Registry[Any], kind: str, version_str: str) -> Any:
    """Parse *version_str* into the value type used by *kind* in *registry*."""
    versions = registry.kind_versions(kind)
    if not versions:
        raise ValueError(f"No versions registered for kind {kind!r}")
    reference = versions[0]
    if isinstance(reference, VersionNode):
        return VersionNode.of(version_str)
    return version_str


class CompoundKeyWalker(WalkerProtocol):
    """Containerless walker: every dict is checked for ``(kind, version)``.

    Only registered compound keys produce entries.  No structural validation
    is performed beyond the presence of the version marker.
    """

    def __init__(
        self,
        registry: Registry[VersionValue],
        *,
        settings: DiscoverySettings,
        direction: MigrationDirectionStrategy = "any",
    ) -> None:
        self._registry = registry
        self._settings = settings
        self._direction = direction

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
                    version_value = _version_value(self._registry, kind, version_str)
                    sentinel = SentinelNode(kind, version_value)
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
                        target = target_resolver(source.kind, source)
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


class PydanticWalker(WalkerProtocol):
    """Container-driven walker that uses a Pydantic model to guide discovery.

    Validates the payload against *container* first, then recursively visits
    fields whose annotations carry ``BaseModel`` subclasses.  Versioned entries
    are extracted from validated sub-dicts.
    """

    def __init__(
        self,
        registry: Registry[VersionValue],
        *,
        settings: DiscoverySettings,
    ) -> None:
        self._registry = registry
        self._settings = settings

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
                if validation_mode == "strict":
                    validated = container.model_validate(data, strict=True).model_dump(
                        by_alias=True
                    )
                else:
                    validated = container.model_validate(data).model_dump(by_alias=True)
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
                    version_value = _version_value(self._registry, kind, version_str)
                    sentinel = SentinelNode(kind, version_value)
                except Exception:
                    sentinel = None
                if sentinel is not None and self._registry.has_model(sentinel):
                    try:
                        source = self._registry.get_model(sentinel)
                    except Exception:
                        pass
                    else:
                        target = target_resolver(source.kind, source)
                        if target is not None:
                            yield (path, depth, source)
                            # Do not recurse into already-discovered entries
                            return

            field_model: type[BaseModel] | None = None
            if parent_model is not None:
                field_info = (
                    parent_model.model_fields.get(str(path[-1])) if path else None
                )
                if field_info is not None:
                    field_model = _resolve_base_model(field_info.annotation)

            for key, nested in value.items():
                child_model = field_model
                if child_model is not None:
                    child_field = child_model.model_fields.get(str(key))
                    if child_field is not None:
                        resolved = _resolve_base_model(child_field.annotation)
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
                field_info = parent_model.model_fields.get(str(path[-1]))
                if field_info is not None:
                    item_model = _resolve_base_model(field_info.annotation)

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
