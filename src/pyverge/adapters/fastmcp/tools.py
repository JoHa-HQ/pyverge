"""Tool factory — register a tool whose injected parameters stay out of the contract.

FastMCP builds a tool's JSON schema from the callable's signature. A
dependency-injected parameter is wiring, not payload, so it must not appear in
that schema — and a non-pydantic injected type (a service) makes schema
generation **fail outright**. FastMCP handles its own ``Depends`` marker; other
DI libraries (dependency-injector's ``Provide``) are not recognized.

``make_tool`` is a drop-in for ``mcp.tool``: it hides detected injected
parameters from the callable's exposed signature and annotations before FastMCP
reflects the tool. Hiding is permanent because FastMCP re-derives the schema
from the same callable on every run; the wired function object is unchanged, so
a direct call still resolves the injected value.

This is a local bridge until FastMCP recognizes foreign injection markers; the
adapter's reflect-time filtering (:mod:`pyverge.adapters.fastmcp.injection`)
remains as a defense for tools registered the plain way.
"""

from __future__ import annotations

import inspect
from typing import Any

from fastmcp.tools.function_tool import FunctionTool

from .injection import InjectionDetector, injected_names


def hide_injected(fn: Any, detector: InjectionDetector | None = None) -> set[str]:
    """Hide injected parameters from *fn*'s exposed signature and annotations.

    FastMCP derives both the tool schema and its run-time validator from the
    callable, so the parameters must be hidden on the callable itself, not only
    on the built tool. Returns the names that were hidden.
    """
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
    """Build a :class:`FunctionTool` excluding injected parameters from the contract.

    Drop-in for ``mcp.tool(fn, name=..., version=...)`` when *fn* has
    dependency-injected parameters. Register the result with
    ``mcp.add_tool(make_tool(...))``. Every other keyword is forwarded to
    ``FunctionTool.from_function``.
    """
    hide_injected(fn, detector)
    return FunctionTool.from_function(fn, name=name, version=version, **kwargs)


__all__ = ["hide_injected", "make_tool"]
