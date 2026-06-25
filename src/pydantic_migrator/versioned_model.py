from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, get_args

from .model_version import ModelVersion
from .types import ModelData, T, V

if TYPE_CHECKING:
    from .model_manager import ModelManager


class VersionedModel(Generic[T, V]):
    """Proxy for container type ``T``, versioned type ``V``, and version metadata."""

    def __init__(
        self,
        manager: ModelManager[T],
        name: str,
        version: str | ModelVersion,
        cls: type[V],
    ) -> None:
        self.manager = manager
        self.name = name
        self.version = (
            ModelVersion.parse(version) if isinstance(version, str) else version
        )
        self.cls = cls

        manager_orig = getattr(manager, "__orig_class__", None)
        self._container_type: Any | None = (
            get_args(manager_orig)[0] if manager_orig else None
        )
        self._versioned_type: type[V] = cls

    def load(self, data: ModelData) -> V:
        return self.cls.model_validate(data)