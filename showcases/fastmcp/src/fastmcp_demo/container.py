"""DI composition root.

``DemoContainer`` is a ``dependency-injector`` ``DeclarativeContainer`` that
builds the settings tree, the tracing adapter and the ``DemoService`` use case.
The service is a ``Singleton`` so the reflection lifecycle runs once; tests
override ``settings`` and swap the tracer for a no-op.
"""

from __future__ import annotations

from dependency_injector import containers, providers

from .adapters import make_tracer
from .application.service import DemoService
from .settings import DemoSettings


class DemoContainer(containers.DeclarativeContainer):
    """Composition root for the showcase application."""

    settings: providers.Singleton[DemoSettings] = providers.Singleton(DemoSettings)

    tracer = providers.Callable(
        make_tracer,
        settings=settings.provided.telemetry,
    )

    demo_service: providers.Singleton[DemoService] = providers.Singleton(
        DemoService,
        settings=settings,
        tracer=tracer,
    )


def build_container(settings: DemoSettings | None = None) -> DemoContainer:
    """Assemble the container, optionally binding an explicit settings tree."""
    container = DemoContainer()
    if settings is not None:
        container.settings.override(settings)
    return container
