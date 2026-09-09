from typing import Any, cast

from pyverge.core import (
    DiscoverySettings,
    MigrationSettings,
    VersionEdge,
    VersioningSettings,
    VersionNode,
    types,
)
from pyverge.migration import (
    CompoundKeyWalker,
    DefaultEntryMigration,
    Engine,
    EntryMigration,
    GraphBuilder,
    JsonSchemaModelAdapter,
    MigrationGraph,
    PydanticDiff,
    PydanticModelAdapter,
    Registry,
    SequentialExecutor,
)


def envelope_model(
    adapter: types.ModelAdapter,
    versioning_settings: VersioningSettings,
    model_cls: type[types.VModel_co] | dict[str, Any],
) -> VersionNode[types.VersionValue, types.ModelBase]:
    """Build a versionable from a model class or a JSON schema.

    A JSON schema document is materialized into a Pydantic model first; a
    model class is wrapped directly.
    """
    if isinstance(model_cls, dict):
        model = cast(JsonSchemaModelAdapter, adapter).to_pydantic(model_cls)
    else:
        model = model_cls
    return cast(
        VersionNode[types.VersionValue, types.ModelBase],
        adapter.versionable(model),
    )


def meta_versionable(
    adapter: types.ModelAdapter,
    kind: str,
    version: str,
) -> VersionNode[types.VersionValue, types.ModelBase]:
    """Build a meta version: a ``(kind, version)`` pair with no concrete model."""
    return VersionNode[types.VersionValue, types.ModelBase](
        _model=None,
        _value=cast(types.VersionValue, adapter.of(version)),
        _kind=kind,
    )


def edge_from_models(
    adapter: types.ModelAdapter,
    versioning_settings: VersioningSettings,
    source_model: type[types.VModel_co] | dict[str, Any],
    target_model: type[types.VModel_co] | dict[str, Any],
    *,
    func: types.MigrationFunc,
    backward_compatible: bool = False,
) -> VersionEdge[types.VersionValue, types.ModelBase, types.ModelBase]:
    """Build a VersionEdge from model classes or JSON schemas.

    *source_model*/*target_model* are either Pydantic model classes or JSON
    schema documents; the JSON schema is materialized into a Pydantic model by
    the adapter at runtime.
    """
    source = envelope_model(adapter, versioning_settings, source_model)
    target = envelope_model(adapter, versioning_settings, target_model)
    return VersionEdge(
        source=source,
        target=target,
        diff=PydanticDiff.from_pair(
            source=source,
            target=target,
            is_backward_compatible=backward_compatible,
        ),
        func=func,
    )


def register_models(
    adapter: types.ModelAdapter,
    registry: Registry[types.VersionValue, types.ModelBase],
    settings: VersioningSettings,
    *models: type[types.VModel_co],
) -> None:
    for model_cls in models:
        registry.store_model(envelope_model(adapter, settings, model_cls))


def default_graph_builder(
    registry: Registry[types.VersionValue, types.ModelBase],
    settings: DiscoverySettings,
    adapter: types.ModelAdapter,
) -> GraphBuilder[types.VersionValue]:
    """Return a graph builder with the standard compound-key walker."""
    return GraphBuilder(
        registry,
        settings,
        CompoundKeyWalker(registry, settings=settings, adapter=adapter),
    )


def make_engine(
    registry: Registry[types.VersionValue, types.ModelBase],
    settings: MigrationSettings,
    adapter: types.ModelAdapter | None = None,
    entry_migration: EntryMigration[types.VersionValue] | None = None,
) -> Engine[types.VersionValue]:
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
        settings,
        SequentialExecutor(),
        default_graph_builder(registry, settings, adapter),
        adapter,
        entry_migration,
    )


def populate_graph(
    adapter: types.ModelAdapter,
    registry: Registry[types.VersionValue, types.ModelBase],
    discovery_settings: DiscoverySettings,
    *models: type[types.VModel_co],
    payload: dict,
    resolver: types.TargetResolver,
    max_depth: int | None = None,
) -> MigrationGraph[types.VersionValue]:
    register_models(adapter, registry, discovery_settings, *models)

    builder = default_graph_builder(registry, discovery_settings, adapter)
    return builder.build(
        payload,
        target_resolver=resolver,
        max_depth=max_depth,
    )
