"""Celery task binding."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from typing import Any

from celery import Task

from pyverge.adapters.handlers import HandlerView
from pyverge.manager.types import TargetPolicy

from .domain import TaskContext
from .runtime import CeleryRuntime
from .targets import TaskTargets


class PyvergeTask(Task):
    """Celery task base that converges its payload and return value."""

    abstract = True
    _pyverge_runtime: CeleryRuntime
    _pyverge_targets: TaskTargets
    _pyverge_payload_name: str | None = None
    _pyverge_payload_index: int | None = None
    _pyverge_return_target: TargetPolicy | None = None

    def _context(self) -> TaskContext:
        request = self.request
        delivery = getattr(request, "delivery_info", None) or {}
        queue = delivery.get("routing_key") if isinstance(delivery, Mapping) else None
        headers = getattr(request, "headers", None) or {}
        return TaskContext(name=self.name or "", queue=queue, headers=headers)

    def _converge_input(
        self,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        target: TargetPolicy,
        context: TaskContext,
    ) -> tuple[tuple[Any, ...], dict[str, Any]]:
        runtime = self._pyverge_runtime
        index = self._pyverge_payload_index
        name = self._pyverge_payload_name
        converted = runtime.context_for(self.request)
        if index is not None and index < len(args):
            value = args[index]
            payload = value if isinstance(value, dict) else runtime.dump(value)
            args = (
                *args[:index],
                runtime.converge_sync(payload, target, context=converted),
                *args[index + 1 :],
            )
        elif name is not None and name in kwargs:
            value = kwargs[name]
            payload = value if isinstance(value, dict) else runtime.dump(value)
            kwargs = {
                **kwargs,
                name: runtime.converge_sync(payload, target, context=converted),
            }
        return args, kwargs

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        runtime = self._pyverge_runtime
        context = self._context()
        target = self._pyverge_targets.select(context)
        args, kwargs = self._converge_input(args, kwargs, target, context)
        result = super().__call__(*args, **kwargs)
        if result is None:
            return None
        source_model = type(result)
        if not runtime.manager.adapter.can_handle(source_model):
            source_model = None
        return runtime.converge_sync(
            runtime.dump(result),
            self._pyverge_return_target or target,
            source_model=source_model,
            context=runtime.context_for(self.request),
        )


def task(  # noqa: PLR0913
    app: Any,
    *,
    runtime: CeleryRuntime,
    target: TargetPolicy = "latest",
    return_target: TargetPolicy | None = None,
    header: str | None = "content-version",
    task_targets: Mapping[str, TargetPolicy] | None = None,
    queue_targets: Mapping[str, TargetPolicy] | None = None,
    payload: str | None = None,
    **options: Any,
) -> Callable[[Callable[..., Any]], Any]:
    """Register a Celery task whose payload and return converge.

    Args:
        app: Celery application.
        runtime: Shared Celery runtime; the task uses its manager.
        target: Default target policy.
        return_target: Target for the task result; defaults to ``target``.
        header: Header used for per-task negotiation.
        task_targets: Target policy per task name.
        queue_targets: Target policy per queue.
        payload: Payload parameter name; defaults to the first parameter.
        **options: Passed to ``app.task``.

    Returns:
        Callable[[Callable[..., Any]], Any]: The Celery task decorator.
    """
    targets = TaskTargets(
        target,
        header=header,
        by_task=task_targets,
        by_queue=queue_targets,
    )

    def decorate(fn: Callable[..., Any]) -> Any:
        signature = inspect.signature(fn)
        name = payload
        if name is None:
            name = next(
                (
                    parameter
                    for parameter, item in signature.parameters.items()
                    if item.kind
                    in (
                        inspect.Parameter.POSITIONAL_ONLY,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    )
                ),
                None,
            )
        index = (
            list(signature.parameters).index(name)
            if name is not None and name in signature.parameters
            else None
        )
        manager = runtime.manager
        view = HandlerView(fn, manager.adapter)
        for model in (view.input_model, view.return_model):
            if model is not None and manager.identifies(model):
                manager.reconcile_model(model)
        base = type(
            "PyvergeTask",
            (PyvergeTask,),
            {
                "_pyverge_runtime": runtime,
                "_pyverge_targets": targets,
                "_pyverge_payload_name": name,
                "_pyverge_payload_index": index,
                "_pyverge_return_target": return_target,
            },
        )
        return app.task(base=base, **options)(fn)

    return decorate


__all__ = ["PyvergeTask", "task"]
