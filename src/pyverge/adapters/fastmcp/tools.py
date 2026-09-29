"""Primitive decorators — build a FastMCP component with injections hidden.

A callable's signature is its contract, but a dependency-injected parameter is
wiring, not payload. These decorators wrap a function into the matching FastMCP
component — tool, prompt or resource — with its injected parameters removed from
the reflected contract, so the primitive only exposes caller-sendable fields.

Apply the decorator **outside** the DI decorator (``@inject``) so it sees the
raw signature::

    @tool(name="search_weather", version="2.0.0")
    @inject
    def search_weather(city: str, weather: WeatherService = Provide[...]) -> dict: ...

Each decorator also works as a plain factory (``tool(fn, name=...)``) for the
case where the function is defined elsewhere.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from fastmcp.prompts.function_prompt import FunctionPrompt
from fastmcp.resources.template import FunctionResourceTemplate
from fastmcp.tools.function_tool import FunctionTool

from .injection import InjectionDetector, injected_names

Component = FunctionTool | FunctionPrompt | FunctionResourceTemplate


def hide_injected(fn: Any, detector: InjectionDetector | None = None) -> set[str]:
    """Strip injected (wired) parameters from *fn*'s reflected signature.

    FastMCP reflects a function's signature into the primitive's contract, so a
    dependency-injected parameter must be removed from it. Returns the names
    that were hidden.
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


def _build(fn: Any, detector: InjectionDetector | None, factory, **kwargs: Any):
    """Hide *fn*'s injected params, then build its component via *factory*."""
    hide_injected(fn, detector)
    return factory(fn, **kwargs)


def tool(
    fn: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    version: str | int | None = None,
    detector: InjectionDetector | None = None,
    **kwargs: Any,
) -> FunctionTool | Callable[[Callable[..., Any]], FunctionTool]:
    """Build a ``FunctionTool`` with injected parameters hidden."""

    def decorate(func: Callable[..., Any]) -> FunctionTool:
        return _build(
            func,
            detector,
            FunctionTool.from_function,
            name=name,
            version=version,
            **kwargs,
        )

    return decorate(fn) if fn is not None else decorate


def prompt(
    fn: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    version: str | int | None = None,
    detector: InjectionDetector | None = None,
    **kwargs: Any,
) -> FunctionPrompt | Callable[[Callable[..., Any]], FunctionPrompt]:
    """Build a ``FunctionPrompt`` with injected parameters hidden."""

    def decorate(func: Callable[..., Any]) -> FunctionPrompt:
        return _build(
            func,
            detector,
            FunctionPrompt.from_function,
            name=name,
            version=version,
            **kwargs,
        )

    return decorate(fn) if fn is not None else decorate


def resource(
    fn: Callable[..., Any] | None = None,
    *,
    uri_template: str,
    name: str | None = None,
    version: str | int | None = None,
    detector: InjectionDetector | None = None,
    **kwargs: Any,
) -> (
    FunctionResourceTemplate | Callable[[Callable[..., Any]], FunctionResourceTemplate]
):
    """Build a ``FunctionResourceTemplate`` with injected parameters hidden."""

    def decorate(func: Callable[..., Any]) -> FunctionResourceTemplate:
        return _build(
            func,
            detector,
            FunctionResourceTemplate.from_function,
            uri_template=uri_template,
            name=name,
            version=version,
            **kwargs,
        )

    return decorate(fn) if fn is not None else decorate


__all__ = ["hide_injected", "prompt", "resource", "tool"]
