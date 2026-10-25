"""Dependency-injector container: brokers, tracing, settings, and features.

Broker and tracer are resources; the manager is the configured **class**; the app
is assembled **last**, instantiating the manager and wiring the features.
"""

from __future__ import annotations

from dependency_injector import containers, providers

from pyverge.settings import MigrationSettings

from .infra.resource import broker_resource, tracer_resource
from .orders import OrdersFeature
from .orders.domain import configure_manager
from .resource import build_faststream


class Container(containers.DeclarativeContainer):
    """Builds and wires the showcase's runtime objects."""

    config = providers.Configuration()

    settings = providers.Factory(
        MigrationSettings,
        direction=config.migration.direction,
        on_missing=config.migration.on_missing,
        version_property=config.migration.version_property,
        kind_property=config.migration.kind_property,
    )

    tracer = providers.Resource(
        tracer_resource,
        config.telemetry.enabled,
        config.telemetry.service_name,
        config.telemetry.endpoint,
    )

    broker = providers.Resource(
        broker_resource,
        config.broker.factory,
        config.broker.dsn,
        config.broker.telemetry.middleware,
        tracer,
    )

    #: The configured manager class; the app assembly instantiates it.
    manager = providers.Singleton(configure_manager, settings)

    orders = providers.Factory(
        OrdersFeature,
        topics=config.broker.topics,
        target=config.broker.convergence.target,
        version_header=config.broker.convergence.header,
    )

    application = providers.Singleton(
        build_faststream,
        service_name=config.telemetry.service_name,
        broker=broker,
        manager_cls=manager,
        tracer=tracer,
        features=providers.List(orders),
    )


__all__ = ["Container"]
