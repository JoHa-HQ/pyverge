"""Composition facade over a FastStream broker."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, TypeVar

from pyverge import Manager
from pyverge.core.registry import HealthFailLevel
from pyverge.runtime import Runner
from pyverge.runtime.manager.types import TargetPolicy

from .domain import Binding, TopicTargets
from .handlers import HandlerView, SignatureBinder
from .ports import HandlerBinder, ResultConverger, TargetSelector
from .publisher import publish_to, publisher
from .runtime import FastStreamRuntime
from .subscriber import subscriber

Fn = TypeVar("Fn", bound=Callable[..., Any])


class PyvergeBroker:
    """Wrap a FastStream broker with pyverge convergence.

    The facade owns one runtime, one binder, and the decoration-time binding
    metadata. Unknown attributes proxy to the wrapped broker, so existing
    FastStream tooling and test brokers keep working.
    """

    def __init__(  # noqa: PLR0913
        self,
        broker: Any,
        manager: Manager | None = None,
        *,
        runtime: FastStreamRuntime | None = None,
        runner: Runner | None = None,
        binder: HandlerBinder | None = None,
        health_fail_level: HealthFailLevel = "error",
    ) -> None:
        if runtime is None:
            if manager is None:
                raise TypeError("PyvergeBroker requires manager= or runtime=")
            runtime = FastStreamRuntime(
                manager, runner, health_fail_level=health_fail_level
            )
        elif manager is not None and manager is not runtime.manager:
            raise ValueError("manager must match runtime.manager")
        elif runner is not None:
            raise ValueError("runner is part of runtime; pass one, not both")
        self._broker = broker
        self._manager = runtime.manager
        self._runtime = runtime
        self._binder = binder or SignatureBinder()
        self._bindings: list[Binding] = []

    @property
    def underlying(self) -> Any:
        """Return the wrapped FastStream broker."""
        return self._broker

    @property
    def manager(self) -> Manager:
        """Return the graph manager."""
        return self._manager

    @property
    def runtime(self) -> FastStreamRuntime:
        """Return the shared convergence runtime."""
        return self._runtime

    @property
    def bindings(self) -> tuple[Binding, ...]:
        """Return the decoration-time binding metadata."""
        return tuple(self._bindings)

    def bind(self, runner: Runner, *, validate_health: bool = True) -> None:
        """Bind the runner created by the application lifespan."""
        self._runtime.bind(runner, validate_health=validate_health)

    def validate_health(self) -> None:
        """Validate registry health using the configured fail level."""
        self._runtime.validate_health()

    def subscriber(
        self,
        *topics: str,
        target: TargetPolicy = "latest",
        targets: TargetPolicy | TopicTargets | None = None,
        header: str | None = None,
        selector: TargetSelector | None = None,
        binder: HandlerBinder | None = None,
        **options: Any,
    ) -> Callable[[Fn], Fn]:
        """Register a converging subscriber."""
        active_targets = target if targets is None else targets
        decorator = subscriber(
            self._broker,
            *topics,
            runtime=self._runtime,
            targets=active_targets,
            header=header,
            selector=selector,
            binder=binder or self._binder,
            **options,
        )

        def decorate(fn: Fn) -> Fn:
            result = decorator(fn)
            self._bindings.append(
                Binding(
                    topics=topics,
                    target=active_targets,
                    input_model=HandlerView(fn, self._manager.adapter).input_model,
                    header=header,
                )
            )
            return result

        return decorate

    def publisher(
        self,
        *topics: str,
        target: TargetPolicy = "latest",
        result_converger: ResultConverger | None = None,
        **options: Any,
    ) -> Callable[[Fn], Any]:
        """Register a converging publisher."""
        decorator = publisher(
            self._broker,
            *topics,
            runtime=self._runtime,
            target=target,
            result_converger=result_converger,
            **options,
        )

        def decorate(fn: Fn) -> Any:
            result = decorator(fn)
            self._bindings.append(
                Binding(
                    topics=topics,
                    target=target,
                    return_model=HandlerView(fn, self._manager.adapter).return_model,
                )
            )
            return result

        return decorate

    def publish_to(
        self,
        *,
        routes: Mapping[str, TargetPolicy],
        version_header: str = "content-version",
    ) -> Callable[[Fn], Fn]:
        """Register a handler that converges independently for each route."""
        decorator = publish_to(
            self._broker,
            runtime=self._runtime,
            routes=routes,
            version_header=version_header,
        )

        def decorate(fn: Fn) -> Fn:
            result = decorator(fn)
            return_model = HandlerView(fn, self._manager.adapter).return_model
            for topic, target in routes.items():
                self._bindings.append(
                    Binding(
                        topics=(topic,),
                        target=target,
                        return_model=return_model,
                    )
                )
            return result

        return decorate

    async def __aenter__(self) -> PyvergeBroker:
        await self._broker.__aenter__()
        return self

    async def __aexit__(self, *exc: Any) -> Any:
        return await self._broker.__aexit__(*exc)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._broker, name)


__all__ = ["PyvergeBroker"]
