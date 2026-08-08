from typing import cast

from pydantic import BaseModel

from pyverge.migration import (
    CompoundKeyWalker,
    DefaultEntryMigration,
    DiscoverySettings,
    Engine,
    EntryMigration,
    GraphBuilder,
    MigrationGraph,
    PydanticDiff,
    PydanticModelAdapter,
    Registry,
    SequentialExecutor,
    VersionEdge,
    VersioningSettings,
    VersionNode,
    types,
)


def envelope_model(
    adapter: types.ModelAdapter,
    versioning_settings: VersioningSettings,
    model_cls: type[types.VModel_co],
) -> VersionNode[types.VersionValue_co, types.VModel_co]:
    version = adapter.of(adapter.version(model_cls))
    kind = adapter.kind(model_cls)
    return VersionNode[types.VersionValue_co, model_cls](
        _model=model_cls,
        _value=cast(types.VersionValue_co, version),
        _kind=kind,
    )


def edge_from_models(
    adapter: types.ModelAdapter,
    versioning_settings: VersioningSettings,
    source_cls: type[types.VModel_co],
    target_cls: type[types.VModel_co],
    *,
    func: types.MigrationFunc,
    backward_compatible: bool = False,
) -> VersionEdge[types.VersionValue_co, types.VModel_co, types.VModel_co]:
    """Build a VersionEdge by wrapping two model classes through
    ``envelope_model`` and computing a ``PydanticDiff``."""
    source = envelope_model(adapter, versioning_settings, source_cls)
    target = envelope_model(adapter, versioning_settings, target_cls)
    return VersionEdge(
        diff=PydanticDiff.from_pair(
            source=source,
            target=target,
            is_backward_compatible=backward_compatible,
        ),
        func=func,
    )


def register_models(
    adapter: types.ModelAdapter,
    registry: Registry[types.VersionValue_co, BaseModel],
    settings: VersioningSettings,
    *models: type[types.VModel_co],
) -> None:
    for model_cls in models:
        registry.store_model(envelope_model(adapter, settings, model_cls))


def default_graph_builder(
    registry: Registry[types.VersionValue_co, BaseModel],
    settings: DiscoverySettings,
    adapter: types.ModelAdapter,
) -> GraphBuilder[types.VersionValue_co]:
    """Return a graph builder with the standard compound-key walker."""
    return GraphBuilder(
        registry,
        settings,
        CompoundKeyWalker(registry, settings=settings, adapter=adapter),
    )


def make_engine(
    registry: Registry[types.VersionValue_co, BaseModel],
    settings: VersioningSettings,
    adapter: types.ModelAdapter | None = None,
    entry_migration: EntryMigration[types.VersionValue_co] | None = None,
) -> Engine[types.VersionValue_co]:
    """Create an engine with the standard walker and sequential executor."""
    if adapter is None:
        adapter = PydanticModelAdapter(
            version_property=settings.version_property,
            kind_property=settings.kind_property,
        )
    if entry_migration is None:
        entry_migration = DefaultEntryMigration()
    return Engine(
        registry,
        settings,  # type: ignore[arg-type]
        SequentialExecutor(),
        default_graph_builder(registry, settings, adapter),  # type: ignore[arg-type]
        adapter,
        entry_migration,
    )


def populate_graph(
    adapter: types.ModelAdapter,
    registry: Registry[types.VersionValue_co, BaseModel],
    discovery_settings: DiscoverySettings,
    *models: type[types.VModel_co],
    payload: dict,
    resolver: types.TargetResolver,
    max_depth: int | None = None,
) -> MigrationGraph[types.VersionValue_co]:
    register_models(adapter, registry, discovery_settings, *models)

    builder = default_graph_builder(registry, discovery_settings, adapter)
    return builder.build(
        payload,
        target_resolver=resolver,
        max_depth=max_depth,
    )
