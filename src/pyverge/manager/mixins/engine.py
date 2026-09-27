"""Engine-lifecycle slice of the composed manager."""

from __future__ import annotations

from typing import TYPE_CHECKING, Generic

from pyverge.types import VersionValue

if TYPE_CHECKING:
    from pyverge.migration.engine import Engine
    from pyverge.types import ManagerClassState, ManagerInstanceState


class EngineLifecycleMixin(Generic[VersionValue]):
    """Construction lifecycle binding each manager to its active engine.

    ``__new__`` resolves the engine — an explicit override, else the class-level
    default established by :meth:`configure`.  ``__init__`` then re-applies an
    explicit override.  Kept apart from target resolution and registration so the
    engine contract can evolve independently of the registration surface.
    """

    if TYPE_CHECKING:
        engine: Engine[VersionValue]

    def __new__(
        cls: type[ManagerClassState[VersionValue]],
        engine: Engine[VersionValue] | None = None,
    ):
        instance = super().__new__(cls)
        instance.engine = engine or cls._default_engine
        return instance

    def __init__(
        self: ManagerInstanceState[VersionValue],
        engine: Engine[VersionValue] | None = None,
    ) -> None:
        """Apply an explicit engine override; ``__new__`` resolves the default."""
        if engine is not None:
            self.engine = engine
