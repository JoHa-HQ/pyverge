from typing import cast

from pydantic_migrator.migration import (
    MigrationSettings,
    TypeInspector,
    VersionedModel,
    types,
)


def envelope_model(
    migration_settings: MigrationSettings, model_cls: type[types.VModel]
) -> VersionedModel[types.VersionValue, types.VModel]:
    version = TypeInspector.get_literal_values(
        model_cls.model_fields[migration_settings.version_property].annotation
    )
    parsed_version = VersionedModel.of(cast(str, version))
    return VersionedModel[types.VersionValue, model_cls](
        _value=cast(types.VersionValue, parsed_version), _model_cls=model_cls
    )
