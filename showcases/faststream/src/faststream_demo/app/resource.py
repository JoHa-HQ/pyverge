from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager

from faststream import FastStream
from opentelemetry.trace import TracerProvider

from pyverge import Manager
from pyverge.adapters.faststream import FastStreamRuntime, PyvergeBroker

from .infra.resource import make_migration_hooks
from .types import Broker


def build_faststream(
    service_name: str,
    broker: Broker,
    manager_cls: type[Manager],
    tracer: TracerProvider | None = None,
    features: Iterable[object] = (),
) -> FastStream:
    manager = manager_cls()
    runtime = FastStreamRuntime(manager, validate_target=True)
    pyverge_broker = PyvergeBroker(broker, runtime=runtime)

    @asynccontextmanager
    async def lifespan() -> AsyncIterator[None]:
        runtime.bind(manager.runner())
        manager.attach_hooks(make_migration_hooks(tracer, service_name))
        yield

    application = FastStream(broker, lifespan=lifespan)
    application.context.set_global("manager", manager)
    application.context.set_global("broker", broker)
    application.context.set_global("pyverge_broker", pyverge_broker)

    for feature in features:
        feature.wire(pyverge_broker)

    return application
