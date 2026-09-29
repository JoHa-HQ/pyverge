"""Primitive decorators — build a FastMCP component with injections hidden.

A dep-injected parameter is wiring, not payload, so it must not appear in the
primitive's reflected contract. Apply the decorator **outside** ``@inject`` so
it sees the raw signature::

    @tool(name="search_weather", version="2.0.0")
    @inject
    def search_weather(city: str, weather: WeatherService = Provide[...]) -> dict: ...

Each decorator is overloaded: given a function it returns the built component
(the ``@tool`` bare form); given only options it returns a decorator
(``@tool(name=...)`` / the factory ``tool(fn, name=...)``).
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, overload

from fastmcp.prompts.function_prompt import FunctionPrompt
from fastmcp.resources.template import FunctionResourceTemplate
from fastmcp.tools.function_tool import FunctionTool

from .injection import InjectionDetector, injected_names

Fn = Callable[..., Any]


def hide_injected(fn: Any, detector: InjectionDetector | None = None) -> set[str]:
    """Strip injected (wired) parameters from *fn*'s reflected signature."""
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


def _build(fn: Fn, detector: InjectionDetector | None, factory: Fn, **kwargs: Any):
    hide_injected(fn, detector)
    return factory(fn, **kwargs)


@overload
def tool(
    fn: Fn,
    *,
    name: str | None = ...,
    version: str | int | None = ...,
    detector: InjectionDetector | None = ...,
    **kwargs: Any,
) -> FunctionTool: ...
@overload
def tool(
    fn: None = None,
    *,
    name: str | None = ...,
    version: str | int | None = ...,
    detector: InjectionDetector | None = ...,
    **kwargs: Any,
) -> Callable[[Fn], FunctionTool]: ...
def tool(
    fn: Fn | None = None,
    *,
    name: str | None = None,
    version: str | int | None = None,
    detector: InjectionDetector | None = None,
    **kwargs: Any,
) -> FunctionTool | Callable[[Fn], FunctionTool]:
    """Build a ``FunctionTool`` with injected parameters hidden."""
    return _decorator(
        fn, FunctionTool.from_function, detector, name=name, version=version, **kwargs
    )


@overload
def prompt(
    fn: Fn,
    *,
    name: str | None = ...,
    version: str | int | None = ...,
    detector: InjectionDetector | None = ...,
    **kwargs: Any,
) -> FunctionPrompt: ...
@overload
def prompt(
    fn: None = None,
    *,
    name: str | None = ...,
    version: str | int | None = ...,
    detector: InjectionDetector | None = ...,
    **kwargs: Any,
) -> Callable[[Fn], FunctionPrompt]: ...
def prompt(
    fn: Fn | None = None,
    *,
    name: str | None = None,
    version: str | int | None = None,
    detector: InjectionDetector | None = None,
    **kwargs: Any,
) -> FunctionPrompt | Callable[[Fn], FunctionPrompt]:
    """Build a ``FunctionPrompt`` with injected parameters hidden."""
    return _decorator(
        fn, FunctionPrompt.from_function, detector, name=name, version=version, **kwargs
    )


@overload
def resource(
    fn: Fn,
    *,
    uri_template: str,
    name: str | None = ...,
    version: str | int | None = ...,
    detector: InjectionDetector | None = ...,
    **kwargs: Any,
) -> FunctionResourceTemplate: ...
@overload
def resource(
    fn: None = None,
    *,
    uri_template: str,
    name: str | None = ...,
    version: str | int | None = ...,
    detector: InjectionDetector | None = ...,
    **kwargs: Any,
) -> Callable[[Fn], FunctionResourceTemplate]: ...
def resource(
    fn: Fn | None = None,
    *,
    uri_template: str,
    name: str | None = None,
    version: str | int | None = None,
    detector: InjectionDetector | None = None,
    **kwargs: Any,
) -> FunctionResourceTemplate | Callable[[Fn], FunctionResourceTemplate]:
    """Build a ``FunctionResourceTemplate`` with injected parameters hidden."""
    return _decorator(
        fn,
        FunctionResourceTemplate.from_function,
        detector,
        uri_template=uri_template,
        name=name,
        version=version,
        **kwargs,
    )


def _decorator(
    fn: Fn | None, factory: Fn, detector: InjectionDetector | None, **kwargs: Any
):
    """Return the built component for *fn*, or the decorator when *fn* is ``None``."""

    def decorate(func: Fn):
        return _build(func, detector, factory, **kwargs)

    return decorate if fn is None else decorate(fn)


__all__ = ["hide_injected", "prompt", "resource", "tool"]
