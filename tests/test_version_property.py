from __future__ import annotations

import operator
from typing import Any

import pytest

from pyverge.migration import (
    PydanticModelAdapter,
    VersioningSettings,
)
from tests.examples.json import (
    ADDRESS_V1_0_0,
    ADDRESS_V2_0_0,
    USER_V0_1_1_DEV_7,
    USER_V1_2_3,
    USER_V2_0_0,
    USER_V2_0_0_BETA_1,
    USER_V2025_01_01,
    USER_V2025_12_31,
    USER_V2026_02_28,
    USER_V2026_03_01,
)
from tests.examples.pydantic.chrono import (
    UserV20250101,
    UserV20251231,
    UserV20260228,
    UserV20260301_120530300Z,
)
from tests.examples.pydantic.semver import (
    UserV011Dev7,
    UserV2,
    UserV123,
    UserV200Beta1,
)
from tests.examples.pydantic.semver_nested import AddressV1, AddressV2
from tests.utils import envelope_model


class TestOperations:
    @pytest.mark.parametrize(
        ("model_adapter", "left", "right", "op"),
        [
            ("pydantic", UserV011Dev7, UserV123, "lt"),
            ("json", USER_V0_1_1_DEV_7, USER_V1_2_3, "lt"),
            ("pydantic", UserV200Beta1, UserV2, "lt"),
            ("json", USER_V2_0_0_BETA_1, USER_V2_0_0, "lt"),
            ("pydantic", UserV011Dev7, UserV011Dev7, "eq"),
            ("json", USER_V0_1_1_DEV_7, USER_V0_1_1_DEV_7, "eq"),
            ("pydantic", UserV20250101, UserV20251231, "lt"),
            ("json", USER_V2025_01_01, USER_V2025_12_31, "lt"),
            ("pydantic", UserV20250101, UserV20250101, "eq"),
            ("json", USER_V2025_01_01, USER_V2025_01_01, "eq"),
        ],
        ids=[
            "dev-lt-pydantic",
            "dev-lt-json",
            "prerelease-lt-pydantic",
            "prerelease-lt-json",
            "dev-eq-pydantic",
            "dev-eq-json",
            "date-lt-pydantic",
            "date-lt-json",
            "date-eq-pydantic",
            "date-eq-json",
        ],
        indirect=["model_adapter"],
    )
    def test_version_operations(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        left: Any,
        right: Any,
        op: str,
    ) -> None:
        comp = getattr(operator, op)
        assert comp(
            envelope_model(model_adapter, versioning_settings, left),
            envelope_model(model_adapter, versioning_settings, right),
        )

    @pytest.mark.parametrize(
        ("model_adapter", "left", "right", "op"),
        [
            ("pydantic", UserV123, UserV20251231, "lt"),
            ("json", USER_V1_2_3, USER_V2025_12_31, "lt"),
            ("pydantic", UserV20250101, UserV123, "gt"),
            ("json", USER_V2025_01_01, USER_V1_2_3, "gt"),
            ("pydantic", UserV123, UserV20250101, "eq"),
            ("json", USER_V1_2_3, USER_V2025_01_01, "eq"),
        ],
        ids=[
            "semver-lt-date-pydantic",
            "semver-lt-date-json",
            "date-gt-semver-pydantic",
            "date-gt-semver-json",
            "semver-eq-date-pydantic",
            "semver-eq-date-json",
        ],
        indirect=["model_adapter"],
    )
    def test_semver_vs_date(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        left: Any,
        right: Any,
        op: str,
    ) -> None:
        with pytest.raises(TypeError):
            left_version = envelope_model(model_adapter, versioning_settings, left)
            right_version = envelope_model(model_adapter, versioning_settings, right)
            comp = getattr(operator, op)
            comp(left_version, right_version)

    @pytest.mark.parametrize(
        ("model_adapter", "models", "expected"),
        [
            (
                "pydantic",
                [UserV200Beta1, UserV123, UserV011Dev7],
                [UserV011Dev7, UserV123, UserV200Beta1],
            ),
            (
                "json",
                [USER_V2_0_0_BETA_1, USER_V1_2_3, USER_V0_1_1_DEV_7],
                [USER_V0_1_1_DEV_7, USER_V1_2_3, USER_V2_0_0_BETA_1],
            ),
            (
                "pydantic",
                [UserV20260228, UserV20250101, UserV20260301_120530300Z],
                [UserV20250101, UserV20260228, UserV20260301_120530300Z],
            ),
            (
                "json",
                [USER_V2026_02_28, USER_V2025_01_01, USER_V2026_03_01],
                [USER_V2025_01_01, USER_V2026_02_28, USER_V2026_03_01],
            ),
        ],
        ids=["semver-pydantic", "semver-json", "date-pydantic", "date-json"],
        indirect=["model_adapter"],
    )
    def test_sortable(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        models: list[Any],
        expected: list[Any],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        expected_versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in expected
        ]
        assert sorted(versions) == expected_versions

    @pytest.mark.parametrize(
        ("model_adapter", "left", "right", "op"),
        [
            ("pydantic", AddressV1, UserV123, "lt"),
            ("json", ADDRESS_V1_0_0, USER_V1_2_3, "lt"),
            ("pydantic", AddressV1, AddressV2, "lt"),
            ("json", ADDRESS_V1_0_0, ADDRESS_V2_0_0, "lt"),
            ("pydantic", UserV123, AddressV1, "gt"),
            ("json", USER_V1_2_3, ADDRESS_V1_0_0, "gt"),
            ("pydantic", UserV011Dev7, UserV123, "lt"),
            ("json", USER_V0_1_1_DEV_7, USER_V1_2_3, "lt"),
            ("pydantic", UserV123, UserV123, "eq"),
            ("json", USER_V1_2_3, USER_V1_2_3, "eq"),
            ("pydantic", UserV20250101, UserV20260301_120530300Z, "lt"),
            ("json", USER_V2025_01_01, USER_V2026_03_01, "lt"),
        ],
        ids=[
            "different_kind_lt-pydantic",
            "different_kind_lt-json",
            "same_kind_different_version_lt-pydantic",
            "same_kind_different_version_lt-json",
            "different_kind_gt-pydantic",
            "different_kind_gt-json",
            "same_kind_different_version_gt-pydantic",
            "same_kind_different_version_gt-json",
            "same_kind_same_version_eq-pydantic",
            "same_kind_same_version_eq-json",
            "same_kind_different_date_lt-pydantic",
            "same_kind_different_date_lt-json",
        ],
        indirect=["model_adapter"],
    )
    def test_different_kind(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        left: Any,
        right: Any,
        op: str,
    ) -> None:
        left_version = envelope_model(model_adapter, versioning_settings, left)
        right_version = envelope_model(model_adapter, versioning_settings, right)
        comp = getattr(operator, op)
        assert comp(left_version, right_version)

    @pytest.mark.parametrize(
        ("model_adapter", "model"),
        [
            ("pydantic", UserV123),
            ("json", USER_V1_2_3),
        ],
        ids=["pydantic", "json"],
        indirect=["model_adapter"],
    )
    def test_incompatible_type(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        subtests: pytest.Subtests,
        model: Any,
    ) -> None:
        """Comparing VersionedModel with an unrelated type raises NotImplementedError."""  # noqa: E501
        v = envelope_model(model_adapter, versioning_settings, model)
        for op, value in [
            ("lt", "not-a-version"),
            ("eq", None),
            ("gt", UserV20251231),
        ]:
            with subtests.test(op=op, value=value):
                with pytest.raises(NotImplementedError):
                    comp = getattr(operator, op)
                    comp(v, value)

    @pytest.mark.parametrize(
        ("model_adapter", "model1", "model2"),
        [
            ("pydantic", UserV123, UserV2),
            ("json", USER_V1_2_3, USER_V2_0_0),
        ],
        ids=["pydantic", "json"],
        indirect=["model_adapter"],
    )
    def test_same_kind_different_version_hash(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        model1: Any,
        model2: Any,
    ) -> None:
        """Same kind, different versions produce distinct hashes."""
        v1 = envelope_model(model_adapter, versioning_settings, model1)
        v2 = envelope_model(model_adapter, versioning_settings, model2)
        assert hash(v1) != hash(v2)

    @pytest.mark.parametrize(
        ("model_adapter", "models", "expected"),
        [
            ("pydantic", [UserV123, UserV011Dev7], 2),
            ("json", [USER_V1_2_3, USER_V0_1_1_DEV_7], 2),
            ("pydantic", [UserV20260228, UserV20250101, UserV20260301_120530300Z], 3),
            ("json", [USER_V2026_02_28, USER_V2025_01_01, USER_V2026_03_01], 3),
        ],
        ids=["semver-pydantic", "semver-json", "date-pydantic", "date-json"],
        indirect=["model_adapter"],
    )
    def test_hashable(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        models: list[Any],
        expected: int,
    ) -> None:
        s = {envelope_model(model_adapter, versioning_settings, m) for m in models}
        assert len(s) == expected
