from typing import cast

from pydantic_migrator.migration import (
    TypeInspector,
    VersionedModel,
    VersioningSettings,
    types,
)


def envelope_model(
    versioning_settings: VersioningSettings, model_cls: type[types.VModel]
) -> VersionedModel[types.VersionValue, types.VModel]:
    version = TypeInspector.get_literal_values(
        model_cls.model_fields[versioning_settings.version_property].annotation
    )
    kind = TypeInspector.get_literal_values(
        model_cls.model_fields[versioning_settings.kind_property].annotation
    )
    parsed_version = VersionedModel.of(cast(str, version))
    return VersionedModel[types.VersionValue, model_cls](
        _model=model_cls,
        _value=cast(types.VersionValue, parsed_version),
        _kind=cast(str, kind),
    )
