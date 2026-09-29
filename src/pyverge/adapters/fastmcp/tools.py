"""Tool factory — keep injected parameters out of the tool contract."""

from __future__ import annotations

import inspect
from typing import Any

from fastmcp.tools.function_tool import FunctionTool

from .injection import InjectionDetector, injected_names


def hide_injected(fn: Any, detector: InjectionDetector | None = None) -> set[str]:
    names = injected_names(fn, detector)
    if not names:
        return names
    signature = inspect.signature(fn)
    fn.__signature__ = signature.replace(
        parameters=[p for n, p in signature.parameters.items() if n not in names]
    )
    annotations = getattr(fn, "__annotations__", None)
    if annotations is not None:
        fn.__annotations__ = {
            name: ann for name, ann in annotations.items() if name not in names
        }
    return names


def make_tool(
    fn: Any,
    *,
    name: str | None = None,
    version: str | int | None = None,
    detector: InjectionDetector | None = None,
    **kwargs: Any,
) -> FunctionTool:
    hide_injected(fn, detector)
    return FunctionTool.from_function(fn, name=name, version=version, **kwargs)


__all__ = ["hide_injected", "make_tool"]
