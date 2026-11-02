"""DI composition root.

``DemoContainer`` is a ``dependency-injector`` ``DeclarativeContainer`` wiring
the whole application: settings, the domain service, the version-graph manager,
the FastMCP server, and the OpenTelemetry tracer. The FastMCP tool in
:mod:`fastmcp_demo.adapters.tools` receives the domain service through FastMCP
native ``Depends``, resolved from the active container.

The server owns its discovery lifecycle: FastMCP enters its lifespan once when
the server is served or driven through a client, so initializing the container
only assembles the app.
"""

from __future__ import annotations

import inspect

from dependency_injector import containers, providers

from .adapters import (
    CallLoggingMiddleware,
    build_server,
    make_call_span_middleware,
    make_migration_hooks,
    make_tracer,
)
from .application.service import DemoService
from .domain import WeatherClient, WeatherService, build_manager
from .settings import DemoSettings


def _call_middleware(span_middleware):
    """Return the host middleware stack, dropping the disabled tracer's None.

    Call logging is always present; the tracing span middleware is added only
    when the tracer is enabled.
    """
    stack = [CallLoggingMiddleware()]
    if span_middleware is not None:
        stack.append(span_middleware)
    return stack


class DemoContainer(containers.DeclarativeContainer):
    """Composition root for the showcase application."""

    settings: providers.Singleton[DemoSettings] = providers.Singleton(DemoSettings)

    # -- domain --------------------------------------------------------------
    weather_client: providers.Singleton[WeatherClient] = providers.Singleton(
        WeatherClient,
        settings=settings.provided.weather,
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
    server = providers.Singleton(
        build_server,
        manager=manager,
        graph=settings.provided.graph,
        server_settings=settings.provided.server,
        hooks=providers.Callable(
            make_migration_hooks,
            tracer=tracer,
            service=settings.provided.telemetry.provided.service_name,
        ),
        middleware=providers.Callable(
            _call_middleware,
            providers.Callable(
                make_call_span_middleware,
                tracer=tracer,
                service=settings.provided.telemetry.provided.service_name,
            ),
        ),
    )

    demo_service: providers.Singleton[DemoService] = providers.Singleton(
        DemoService,
        settings=settings,
        manager=manager,
        server=server,
    )


_active_container: DemoContainer | None = None


def current_weather_service() -> WeatherService:
    """Resolve the weather service from the active container."""
    if _active_container is None:
        raise RuntimeError("demo container has not been built")
    return _active_container.weather_service()


def build_container(settings: DemoSettings | None = None) -> DemoContainer:
    """Assemble the container, optionally binding an explicit settings tree."""
    global _active_container  # noqa: PLW0603
    container = DemoContainer()
    if settings is not None:
        container.settings.override(settings)
    _active_container = container
    return container


async def resolve_prepared(container: DemoContainer) -> DemoService:
    """Initialize the container and return its ready service."""
    init = container.init_resources()
    if inspect.isawaitable(init):
        await init
    return container.demo_service()


async def shutdown_container(container: DemoContainer) -> None:
    """Flush and stop all allocated providers, awaiting async resources.

    ``shutdown_resources()`` returns ``None`` when no async resource was ever
    initialized (nothing to await), and an awaitable otherwise.
    """
    shutdown = container.shutdown_resources()
    if inspect.isawaitable(shutdown):
        await shutdown
