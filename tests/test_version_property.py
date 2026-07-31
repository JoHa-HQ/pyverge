from __future__ import annotations

import operator
from typing import Literal

import pytest
from pendulum import Date
from pydantic import BaseModel
from semver import Version

from pyverge.migration import (
    PydanticDiff,
    PydanticModelAdapter,
    VersionEdge,
    VersioningSettings,
    types,
)
from tests.examples.pydantic.chrono import (
    UserV20250101,
    UserV20250310,
    UserV20251231,
    UserV20260228,
    UserV20260301_120530300Z,
)
from tests.examples.pydantic.semver import (
    UserV011Dev7,
    UserV1,
    UserV2,
    UserV3,
    UserV123,
    UserV200Beta1,
)
from tests.examples.pydantic.semver_nested import AddressV1, AddressV2
from tests.utils import envelope_model


class TestParse:
    @pytest.mark.parametrize(
        ("model", "expected_str"),
        [
            (UserV123, "User:1.2.3"),
            (UserV200Beta1, "User:2.0.0-beta.1"),
            (UserV011Dev7, "User:0.1.1+dev.7"),
        ],
        ids=["simple", "prerelease", "dev"],
    )
    def test_parse_semver(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        model: type[types.VModel_co],
        expected_str: str,
    ) -> None:
        v = envelope_model(model_adapter, versioning_settings, model)
        assert str(v) == expected_str

    @pytest.mark.parametrize(
        ("model", "expected_str"),
        [
            (UserV20250101, "User:2025-01-01"),
            (UserV20260228, "User:2026-02-28"),
            (UserV20260301_120530300Z, "User:2026-03-01"),
        ],
        ids=["without-time", "leap-year", "with-time"],
    )
    def test_parse_date(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        model: type[types.VModel_co],
        expected_str: str,
    ) -> None:
        v = envelope_model(model_adapter, versioning_settings, model)
        assert str(v) == expected_str

    def test_invalid_semver_models(
        self,
        model_adapter: PydanticModelAdapter,
        subtests: pytest.Subtests,
        versioning_settings: VersioningSettings,
    ) -> None:

        class InvalidBetaModel(BaseModel):
            kind: Literal["beta"]
            version: Literal["beta.7"]

        class InvalidAlphaModel(BaseModel):
            kind: Literal["alpha"]
            version: Literal["0.0.0.alpha7"]

        for model in [InvalidBetaModel, InvalidAlphaModel]:
            with subtests.test(f"invalid-semver-version: {model.__name__}"):
                with pytest.raises(ValueError):
                    envelope_model(model_adapter, versioning_settings, model)

    def test_invalid_date_models(
        self,
        model_adapter: PydanticModelAdapter,
        subtests: pytest.Subtests,
        versioning_settings: VersioningSettings,
    ) -> None:

        class InvalidTimeModel(BaseModel):
            kind: Literal["time"]
            version: Literal["15:15:20.000Z"]

        for model in [InvalidTimeModel]:
            with subtests.test(f"invalid-date-version: {model.__name__}"):
                with pytest.raises(ValueError):
                    envelope_model(model_adapter, versioning_settings, model)


class TestOperations:
    @pytest.mark.parametrize(
        ("left", "right", "op"),
        [
            # Semver comparison
            (UserV011Dev7, UserV123, "lt"),
            (UserV200Beta1, UserV2, "lt"),
            (UserV011Dev7, UserV011Dev7, "eq"),
            # Chrono comparison
            (UserV20250101, UserV20251231, "lt"),
            (UserV20250101, UserV20250101, "eq"),
        ],
    )
    def test_version_operations(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        left: type[types.VModel_co],
        right: type[types.VModel_co],
        op: str,
    ) -> None:
        comp = getattr(operator, op)
        assert comp(
            envelope_model(model_adapter, versioning_settings, left),
            envelope_model(model_adapter, versioning_settings, right),
        )

    @pytest.mark.parametrize(
        "left, right, op",
        [
            (UserV123, UserV20251231, "lt"),
            (UserV20250101, UserV123, "gt"),
            (UserV123, UserV20250101, "eq"),
        ],
    )
    def test_semver_vs_date(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        left: type[types.VModel_co],
        right: type[types.VModel_co],
        op: str,
    ) -> None:
        with pytest.raises(TypeError):
            left_version = envelope_model(model_adapter, versioning_settings, left)
            right_version = envelope_model(model_adapter, versioning_settings, right)
            comp = getattr(operator, op)
            comp(left_version, right_version)

    @pytest.mark.parametrize(
        "models, expected",
        [
            (
                [UserV200Beta1, UserV123, UserV011Dev7],
                [UserV011Dev7, UserV123, UserV200Beta1],
            ),
            (
                [UserV20260228, UserV20250101, UserV20260301_120530300Z],
                [UserV20250101, UserV20260228, UserV20260301_120530300Z],
            ),
        ],
    )
    def test_sortable(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        models: list[type[types.VModel_co]],
        expected: list[type[types.VModel_co]],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, model)
            for model in models
        ]
        expected_versions = [
            envelope_model(model_adapter, versioning_settings, model)
            for model in expected
        ]
        assert sorted(versions) == expected_versions

    @pytest.mark.parametrize(
        "left, right, op",
        [
            (AddressV1, UserV123, "lt"),
            (AddressV1, AddressV2, "lt"),
            (UserV123, AddressV1, "gt"),
            (UserV011Dev7, UserV123, "lt"),
            (UserV123, UserV123, "eq"),
            (UserV20250101, UserV20260301_120530300Z, "lt"),
        ],
        ids=[
            "different_kind_lt",
            "same_kind_different_version_lt",
            "different_kind_gt",
            "same_kind_different_version_gt",
            "same_kind_same_version_eq",
            "same_kind_different_date_lt",
        ],
    )
    def test_different_kind(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        left: type[types.VModel_co],
        right: type[types.VModel_co],
        op: str,
    ) -> None:
        left_version = envelope_model(model_adapter, versioning_settings, left)
        right_version = envelope_model(model_adapter, versioning_settings, right)
        comp = getattr(operator, op)
        assert comp(left_version, right_version)

    def test_incompatible_type(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
    ) -> None:
        """
        Comparing VersionedModel with an unrelated type raises NotImplementedError.
        """
        v = envelope_model(model_adapter, versioning_settings, UserV123)
        for op, value, exception in [
            ("lt", "not-a-version", pytest.raises(NotImplementedError)),
            ("eq", None, pytest.raises(NotImplementedError)),
            ("gt", UserV20251231, pytest.raises(NotImplementedError)),
        ]:
            with exception:
                comp = getattr(operator, op)
                comp(v, value)

    def test_same_kind_different_version_hash(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
    ) -> None:
        """Same kind, different versions produce distinct hashes."""
        v1 = envelope_model(model_adapter, versioning_settings, UserV123)
        v2 = envelope_model(model_adapter, versioning_settings, UserV2)
        assert hash(v1) != hash(v2)

    @pytest.mark.parametrize(
        "models, expected",
        [
            ([UserV123, UserV011Dev7], 2),
            ([UserV20260228, UserV20250101, UserV20260301_120530300Z], 3),
        ],
    )
    def test_hashable(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        models: list[type[types.VModel_co]],
        expected: int,
    ) -> None:
        s = {
            envelope_model(model_adapter, versioning_settings, model)
            for model in models
        }
        assert len(s) == expected


class TestRepresentation:
    @pytest.mark.parametrize(
        ("model", "expected_str", "expected_repr"),
        [
            (UserV123, "User:1.2.3", "VersionNode[Version, UserV123](1.2.3, User)"),
            (
                UserV20251231,
                "User:2025-12-31",
                "VersionNode[Date, UserV20251231](2025-12-31, User)",
            ),
            (
                UserV200Beta1,
                "User:2.0.0-beta.1",
                "VersionNode[Version, UserV200Beta1](2.0.0-beta.1, User)",
            ),
        ],
        ids=["semver", "date", "prerelease"],
    )
    def test_str_repr(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        model: type[types.VModel_co],
        expected_str: str,
        expected_repr: str,
    ) -> None:
        v = envelope_model(model_adapter, versioning_settings, model)
        assert str(v) == expected_str
        assert repr(v) == expected_repr

    @pytest.mark.parametrize(
        "model, expected_strategy",
        [(UserV123, Version), (UserV20251231, Date), (UserV200Beta1, Version)],
        ids=["semver", "date", "prerelease"],
    )
    def test_print_strategy(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        model: type[types.VModel_co],
        expected_strategy: str,
    ) -> None:
        v = envelope_model(model_adapter, versioning_settings, model)
        assert v.strategy == expected_strategy


class TestMigrationEdge:
    """Tests for ``MigrationEdge`` — construction, comparison, hashing, string."""

    @pytest.mark.parametrize(
        "source_model, target_model",
        [
            (UserV1, UserV2),
            (UserV20250310, UserV20251231),
        ],
        ids=["semver", "date"],
    )
    def test_construct_same_kind(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        source_model: type[types.VModel],
        target_model: type[types.VModel],
    ) -> None:
        """Construction succeeds when source and target share the same kind."""

        source = envelope_model(model_adapter, versioning_settings, source_model)
        target = envelope_model(model_adapter, versioning_settings, target_model)
        diff = PydanticDiff.from_pair(source, target)
        edge = VersionEdge(diff, func=lambda d: d)
        assert edge.source is source
        assert edge.target is target

    @pytest.mark.parametrize(
        "source_model, target_model",
        [
            (UserV1, UserV20250101),
            (AddressV1, UserV1),
        ],
        ids=["across-strategy", "across-kinds"],
    )
    def test_construct_across_kinds_and_strategy_raises(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        source_model: type[types.VModel],
        target_model: type[types.VModel],
    ) -> None:
        """Construction fails when source and target have different kinds."""
        source = envelope_model(model_adapter, versioning_settings, source_model)
        target = envelope_model(model_adapter, versioning_settings, target_model)
        with pytest.raises(ValueError):
            PydanticDiff.from_pair(source, target)

    @pytest.mark.parametrize(
        "source_model, target_model",
        [
            (UserV1, UserV2),
            (UserV20250310, UserV20251231),
        ],
        ids=["semver", "date"],
    )
    def test_kind_property(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        source_model: type[types.VModel],
        target_model: type[types.VModel],
    ) -> None:
        """The kind property returns the source's kind."""
        source = envelope_model(model_adapter, versioning_settings, source_model)
        target = envelope_model(model_adapter, versioning_settings, target_model)
        diff = PydanticDiff.from_pair(source, target)
        edge = VersionEdge(diff, func=lambda d: d)
        assert edge.kind == diff.source.kind

    @pytest.mark.parametrize(
        ("source_model", "target_model", "expected_str"),
        [
            (UserV1, UserV2, "VersionEdge(User:1.0.0→User:2.0.0)"),
            (
                UserV20250310,
                UserV20251231,
                "VersionEdge(User:2025-03-10→User:2025-12-31)",
            ),
        ],
        ids=["semver", "date"],
    )
    def test_str(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        source_model: type[types.VModel],
        target_model: type[types.VModel],
        expected_str: str,
    ) -> None:
        """String representation shows source→target."""
        source = envelope_model(model_adapter, versioning_settings, source_model)
        target = envelope_model(model_adapter, versioning_settings, target_model)
        diff = PydanticDiff.from_pair(source, target)
        edge = VersionEdge(diff, func=lambda d: d)
        assert str(edge) == expected_str

    @pytest.mark.parametrize(
        ("left_src", "left_tgt", "right_src", "right_tgt", "op"),
        [
            # Same source, different target
            (UserV1, UserV2, UserV1, UserV3, "lt"),
            (UserV1, UserV3, UserV1, UserV2, "gt"),
            # Different source
            (UserV1, UserV2, UserV2, UserV3, "lt"),
            (UserV2, UserV3, UserV1, UserV2, "gt"),
            # Same edge — equal
            (UserV1, UserV2, UserV1, UserV2, "eq"),
            # Different edge — not equal
            (UserV1, UserV2, UserV1, UserV3, "ne"),
        ],
        ids=[
            "same_source_lt",
            "same_source_gt",
            "diff_source_lt",
            "diff_source_gt",
            "same_edge_eq",
            "diff_edge_ne",
        ],
    )
    def test_comparison(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        left_src: type[types.VModel],
        left_tgt: type[types.VModel],
        right_src: type[types.VModel],
        right_tgt: type[types.VModel],
        op: str,
    ) -> None:
        """MigrationEdge comparison follows (source, target) tuple ordering."""
        left = VersionEdge(
            diff=PydanticDiff.from_pair(
                envelope_model(model_adapter, versioning_settings, left_src),
                envelope_model(model_adapter, versioning_settings, left_tgt),
            ),
            func=lambda d: d,
        )
        right = VersionEdge(
            diff=PydanticDiff.from_pair(
                envelope_model(model_adapter, versioning_settings, right_src),
                envelope_model(model_adapter, versioning_settings, right_tgt),
            ),
            func=lambda d: d,
        )
        comp = getattr(operator, op)
        assert comp(left, right)

    @pytest.mark.parametrize(
        "nodes, op",
        [
            [[(UserV1, UserV2), (UserV1, UserV2)], "eq"],
            [[(UserV1, UserV2), (UserV2, UserV1)], "ne"],
        ],
        ids=["equal", "not_equal"],
    )
    def test_hash(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        nodes: tuple[type[types.VModel], type[types.VModel]],
        op: str,
    ) -> None:
        """Edges with the same source and target have the same hash."""
        comp = getattr(operator, op)
        hashes = [
            hash(e)
            for e in [
                VersionEdge(
                    diff=PydanticDiff.from_pair(
                        *[
                            envelope_model(model_adapter, versioning_settings, el)
                            for el in nodes[0]
                        ]
                    ),
                    func=lambda d: d,
                ),
                VersionEdge(
                    diff=PydanticDiff.from_pair(
                        *[
                            envelope_model(model_adapter, versioning_settings, el)
                            for el in nodes[1]
                        ]
                    ),
                    func=lambda d: {"x": 1},
                ),
            ]
        ]
        assert comp(*hashes)

    @pytest.mark.parametrize(
        "source_model, target_model, expected",
        [
            (
                [UserV1, UserV2, UserV1],
                [UserV2, UserV3, UserV2],
                2,
            ),
            (
                [UserV20250310, UserV20250101],
                [UserV20251231, UserV20251231],
                2,
            ),
        ],
        ids=["semver", "date"],
    )
    def test_hashable_in_set(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        source_model: list[type[types.VModel]],
        target_model: list[type[types.VModel]],
        expected: int,
    ) -> None:
        """MigrationEdge can be stored in a set; duplicates collapse."""
        edges = {
            VersionEdge(
                diff=PydanticDiff.from_pair(
                    envelope_model(model_adapter, versioning_settings, s),
                    envelope_model(model_adapter, versioning_settings, t),
                ),
                func=lambda d: d,
            )
            for s, t in zip(source_model, target_model)
        }
        assert len(edges) == expected

    @pytest.mark.parametrize(
        "source_model, target_model",
        [
            (UserV1, UserV2),
            (UserV2, UserV1),
        ],
        ids=["forward", "backward"],
    )
    def test_is_forward(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        source_model: type[types.VModel],
        target_model: type[types.VModel],
    ) -> None:
        """is_forward is True when source < target."""
        source = envelope_model(model_adapter, versioning_settings, source_model)
        target = envelope_model(model_adapter, versioning_settings, target_model)
        diff = PydanticDiff.from_pair(
            source=source,
            target=target,
        )
        edge = VersionEdge(diff=diff, func=lambda d: d)
        assert edge.diff.is_forward == (source < target)

    @pytest.mark.parametrize(
        "source_model, target_model",
        [
            (UserV1, UserV2),
            (UserV2, UserV1),
        ],
        ids=["forward", "backward"],
    )
    def test_is_backward(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        source_model: type[types.VModel],
        target_model: type[types.VModel],
    ) -> None:
        """is_backward is True when source > target."""
        source = envelope_model(model_adapter, versioning_settings, source_model)
        target = envelope_model(model_adapter, versioning_settings, target_model)
        diff = PydanticDiff.from_pair(
            source=source,
            target=target,
        )
        edge = VersionEdge(diff=diff, func=lambda d: d)
        assert edge.diff.is_backward == (source > target)

    def test_func_stored(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
    ) -> None:
        """The migration function is stored as edge.func."""
        source = envelope_model(model_adapter, versioning_settings, UserV1)
        target = envelope_model(model_adapter, versioning_settings, UserV2)

        def _migrate(data: dict) -> dict:
            data["migrated"] = True
            return data

        edge = VersionEdge(
            diff=PydanticDiff.from_pair(source, target),
            func=_migrate,
        )
        assert edge.func is _migrate

    def test_call_delegates_to_func(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
    ) -> None:
        """Calling the edge delegates to the stored migration function."""
        source = envelope_model(model_adapter, versioning_settings, UserV1)
        target = envelope_model(model_adapter, versioning_settings, UserV2)

        def _migrate(data: dict) -> dict:
            data["migrated"] = True
            return data

        edge = VersionEdge(
            diff=PydanticDiff.from_pair(source, target),
            func=_migrate,
        )
        result = edge({"version": "1.0.0"})
        assert result["migrated"] is True

    def test_call_roundtrips(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
    ) -> None:
        """Calling the edge is identical to calling edge.func directly."""
        source = envelope_model(model_adapter, versioning_settings, UserV1)
        target = envelope_model(model_adapter, versioning_settings, UserV2)

        def _migrate(data: dict) -> dict:
            data["age"] = None
            return data

        edge = VersionEdge(
            diff=PydanticDiff.from_pair(source, target),
            func=_migrate,
        )
        data = {"version": "1.0.0", "name": "Alice"}
        assert edge(data) == edge.func(data)


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
        patch = diff.render()
        serialized = patch()
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
