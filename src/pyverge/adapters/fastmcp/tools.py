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

    def decorate(func: Fn):
        hide_injected(func, detector)
        return factory(func, **kwargs)

    return decorate if fn is None else decorate(fn)


__all__ = ["hide_injected", "prompt", "resource", "tool"]
