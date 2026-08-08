import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from pyverge.migration import ModelManager


class ConfigError(Exception):
    """Configuration loading error."""


def resolve_manager(spec: str) -> ModelManager:
    """Resolve a manager from a ``module_path:object_path`` spec."""

    if ":" not in spec:
        raise ConfigError(f"Manager spec must be 'module:object_path', got '{spec}'")

    module_path, object_path = spec.split(":", 1)
    cwd = Path.cwd()
    module = _import_module(cwd, module_path)
    obj: Any = module
    for part in object_path.split("."):
        obj = getattr(obj, part)
    if not isinstance(obj, ModelManager):
        raise ConfigError(
            f"Manager '{spec}' resolved to {type(obj).__name__}, "
            "expected a ModelManager"
        )
    return obj


def _import_module(cwd: Path, module_path: str) -> ModuleType:
    """Import a module, falling back to a local file when not on the path."""
    try:
        return importlib.import_module(module_path)
    except ImportError as e:
        module_file = cwd / module_path.replace(".", "/")
        if not module_file.suffix:
            module_file = module_file.with_suffix(".py")

        if not module_file.exists():
            raise ConfigError(f"Cannot import module '{module_path}': {e}") from e

        spec = importlib.util.spec_from_file_location(module_path, module_file)
        if spec is None or spec.loader is None:
            raise ConfigError(f"Cannot load module from {module_file}") from e

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_path] = module
        spec.loader.exec_module(module)
        return module


def list_managers_from_module(module_path: str) -> list[str]:
    """Return the names of ``ModelManager`` instances/subclasses in *module_path*."""
    module = importlib.import_module(module_path)
    return [
        name
        for name, value in vars(module).items()
        if isinstance(value, ModelManager)
        or (isinstance(value, type) and issubclass(value, ModelManager))
    ]
