"""Tests for the Pydantic model adapter and its diff."""

from __future__ import annotations

import pendulum
import pytest
import semver
from pydantic import BaseModel

from pyverge.core import (
    VersioningSettings,
    types,
)
from pyverge.migration import (
    Diff,
    PydanticDiff,
    PydanticModelAdapter,
    Registry,
)
from tests.examples.pydantic.chrono import (
    UserV20250310,
    UserV20251231,
)
from tests.examples.pydantic.semver import (
    UserV1,
    UserV2,
    UserV3,
    UserV123,
)
from tests.utils import envelope_model, meta_versionable


class TestPydanticDiff:
    """Tests for ``PydanticDiff`` — construction, predicates, rendering."""

    @pytest.mark.parametrize(
        "source_model, target_model",
        [
            (UserV1, UserV123),
            (UserV20250310, UserV20251231),
        ],
        ids=["semver", "date"],
    )
    def test_from_pair_detects_added_field(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        source_model: type[types.VModel],
        target_model: type[types.VModel],
    ) -> None:
        """from_pair detects a field present in target but not source."""
        source = envelope_model(model_adapter, versioning_settings, source_model)
        target = envelope_model(model_adapter, versioning_settings, target_model)

        diff = PydanticDiff.from_pair(source=source, target=target)
        assert diff.has_additions
        assert "last_name" in diff.added_fields

    @pytest.mark.parametrize(
        "source_model, target_model",
        [
            (UserV123, UserV1),
            (UserV20251231, UserV20250310),
        ],
        ids=["semver", "date"],
    )
    def test_from_pair_detects_removed_field(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        source_model: type[types.VModel],
        target_model: type[types.VModel],
    ) -> None:
        """from_pair detects a field present in source but not target."""
        source = envelope_model(model_adapter, versioning_settings, source_model)
        target = envelope_model(model_adapter, versioning_settings, target_model)

        diff = PydanticDiff.from_pair(source=source, target=target)
        assert diff.has_removals
        assert "last_name" in diff.removed_fields

    def test_is_identity_for_same_model(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
    ) -> None:
        """from_pair returns identity diff when models are identical."""
        version = envelope_model(model_adapter, versioning_settings, UserV1)

        diff = PydanticDiff.from_pair(source=version, target=version)
        assert diff.is_identity
        assert not diff.has_additions
        assert not diff.has_removals
        assert not diff.has_modifications

    def test_added_default(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
    ) -> None:
        """added_default returns the default for a newly added field."""
        source = envelope_model(model_adapter, versioning_settings, UserV1)
        target = envelope_model(model_adapter, versioning_settings, UserV2)

        diff = PydanticDiff.from_pair(source=source, target=target)
        assert diff.added_default("age") is None

    def test_added_required(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
    ) -> None:
        """is_added_required identifies required new fields."""
        source = envelope_model(model_adapter, versioning_settings, UserV1)
        target = envelope_model(model_adapter, versioning_settings, UserV3)

        diff = PydanticDiff.from_pair(source=source, target=target)
        assert "status" in diff.added_fields
        assert diff.added_default("status") == "active"

    def test_render_json_patch(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
    ) -> None:
        """Default renderer produces RFC 6902 JSON Patch."""
        source = envelope_model(model_adapter, versioning_settings, UserV1)
        target = envelope_model(model_adapter, versioning_settings, UserV2)

        diff = PydanticDiff.from_pair(source=source, target=target)
        serialized = diff.render()
        assert isinstance(serialized, list)
        add_ops = [op for op in serialized if op["op"] == "add"]
        assert any(op["path"] == "/age" for op in add_ops)

    def test_source_and_target_on_diff(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
    ) -> None:
        """The diff stores source and target Versionable references."""
        source = envelope_model(model_adapter, versioning_settings, UserV1)
        target = envelope_model(model_adapter, versioning_settings, UserV2)

        diff = PydanticDiff.from_pair(source=source, target=target)
        assert diff.source is source
        assert diff.target is target

    def test_edge_property(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
    ) -> None:
        """edge returns the (source_version, target_version) MigrationKey tuple."""
        source = envelope_model(model_adapter, versioning_settings, UserV1)
        target = envelope_model(model_adapter, versioning_settings, UserV2)

        diff = PydanticDiff.from_pair(source=source, target=target)
        assert diff.edge == (source, target)

    @pytest.mark.parametrize(
        "registry, version",
        [
            [Registry[semver.Version, BaseModel](), "0.1.0"],
            [Registry[pendulum.Date, BaseModel](), "2024-01-01"],
        ],
    )
    def test_meta_endpoint_produces_empty_diff(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue, BaseModel],
        version: str,
    ) -> None:
        """A meta endpoint yields a plain Diff with empty predicates."""
        meta = meta_versionable(model_adapter, "User", version)
        real = envelope_model(model_adapter, versioning_settings, UserV1)

        diff = model_adapter.diff(meta, real)
        assert isinstance(diff, Diff)
        assert not diff.has_additions
        assert not diff.has_removals
        assert not diff.has_modifications
