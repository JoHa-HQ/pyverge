"""FastStream showcase for pyverge."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .app import app, create_app
    from .container import Container

__all__ = ["Container", "app", "create_app"]


def __getattr__(name: str):
    if name in {"app", "create_app"}:
        from .app import app as _app  # noqa: PLC0415
        from .app import create_app as _create_app  # noqa: PLC0415

        return _app if name == "app" else _create_app
    if name == "Container":
        from .container import Container as _Container  # noqa: PLC0415

        return _Container
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
