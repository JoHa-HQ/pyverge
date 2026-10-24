"""Build discovery: descriptor interpretation and registration."""

from .strategies import (
    CompositeStrategy,
    MigrationStrategy,
    ModelSchemaStrategy,
    RoutesStrategy,
    TablesStrategy,
    TopicsStrategy,
)
from .types import (
    DescriptorStrategy,
    ReflectionReport,
    ReflectionStrategy,
    RegistrationContext,
    RegistrationPort,
    SourceDescriptor,
    SourcePort,
    SourceVisitor,
)
from .visitor import RegistrationVisitor

__all__ = [
    "CompositeStrategy",
    "DescriptorStrategy",
    "MigrationStrategy",
    "ModelSchemaStrategy",
    "ReflectionReport",
    "ReflectionStrategy",
    "RegistrationContext",
    "RegistrationPort",
    "RegistrationVisitor",
    "RoutesStrategy",
    "SourceDescriptor",
    "SourcePort",
    "SourceVisitor",
    "TablesStrategy",
    "TopicsStrategy",
]
