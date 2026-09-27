"""DI composition root.

``DemoContainer`` is a ``dependency-injector`` ``DeclarativeContainer`` wiring
the whole application: settings, the domain service, the version-graph manager,
the FastMCP registry and server, and the OpenTelemetry tracer. The FastMCP tool
in :mod:`fastmcp_demo.adapters.tools` receives the domain service through
wiring (``@inject`` + ``Provide``), so no component reaches for its own
dependencies.

``prepared`` is an :class:`~dependency_injector.resources.AsyncResource` that
runs the reflection lifecycle once, so callers only need
``await container.init_resources()`` to get a ready server.
"""

from __future__ import annotations

import inspect

from dependency_injector import containers, providers, resources

from .adapters import (
    build_registry,
    build_server,
    make_migration_hooks,
    make_span_factory,
    make_tracer,
)
from .adapters import tools as tools_module
from .application.service import DemoService
from .domain import WeatherClient, WeatherService, build_manager
from .settings import DemoSettings


class _Prepared(resources.AsyncResource[DemoService]):
    """Async resource that runs the demo lifecycle exactly once."""

    def __init__(self, service: DemoService) -> None:
        super().__init__()
        self._service = service

    async def init(self) -> DemoService:
        await self._service.prepare()
        return self._service

    async def shutdown(self, resource: DemoService | None) -> None:
        return None


class DemoContainer(containers.DeclarativeContainer):
    """Composition root for the showcase application."""

    wiring_config = containers.WiringConfiguration(modules=[tools_module])

    settings: providers.Singleton[DemoSettings] = providers.Singleton(DemoSettings)

    # -- domain --------------------------------------------------------------
    weather_client: providers.Singleton[WeatherClient] = providers.Singleton(
        WeatherClient
    )
    weather_service: providers.Singleton[WeatherService] = providers.Singleton(
        WeatherService,
        client=weather_client,
    )
    manager = providers.Singleton(
        build_manager,
        graph=settings.provided.graph,
    )

    tracer = providers.Singleton(
        make_tracer,
        settings=settings.provided.telemetry,
    )
    registry = providers.Singleton(
        build_registry,
        manager=manager,
        graph=settings.provided.graph,
        hooks=providers.Callable(
            make_migration_hooks,
            tracer=tracer,
            service=settings.provided.telemetry.provided.service_name,
        ),
    )
    server = providers.Singleton(
        build_server,
        registry=registry,
        graph=settings.provided.graph,
        span_factory=providers.Callable(
            make_span_factory,
            tracer=tracer,
            service=settings.provided.telemetry.provided.service_name,
        ),
    )

    demo_service: providers.Singleton[DemoService] = providers.Singleton(
        DemoService,
        settings=settings,
        manager=manager,
        registry=registry,
        server=server,
    )
    prepared: providers.Resource[DemoService] = providers.Resource(
        _Prepared,
        service=demo_service,
    )


def build_container(settings: DemoSettings | None = None) -> DemoContainer:
    """Assemble the container, optionally binding an explicit settings tree."""
    container = DemoContainer()
    if settings is not None:
        container.settings.override(settings)
    return container


async def resolve_prepared(container: DemoContainer) -> DemoService:
    """Initialize the container and return the prepared ``DemoService``.

    Async resources expose their value as an awaitable once
    ``init_resources()`` has run; this collapses the two steps into one call
    for the CLI and tests.
    """
    init = container.init_resources()
    if inspect.isawaitable(init):
        await init
    prepared = container.prepared()
    if inspect.isawaitable(prepared):
        return await prepared
    return prepared


async def shutdown_container(container: DemoContainer) -> None:
    """Flush and stop all allocated providers, awaiting async resources.

    ``shutdown_resources()`` returns ``None`` when no async resource was ever
    initialized (nothing to await), and an awaitable otherwise.
    """
    shutdown = container.shutdown_resources()
    if inspect.isawaitable(shutdown):
        await shutdown
