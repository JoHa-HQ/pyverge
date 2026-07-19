from __future__ import annotations

import operator
from typing import Literal

import pytest
from pendulum import Date
from pydantic import BaseModel
from semver import Version

from pydantic_migrator.migration import MigrationSettings, types
from tests.examples.chronnological import (
    UserV20250101,
    UserV20251231,
    UserV20260228,
    UserV20260301_120530300Z,
)
from tests.examples.semver import UserV011Dev7, UserV2, UserV123, UserV200Beta1
from tests.utils import envelope_model


class TestParse:
    @pytest.mark.parametrize(
        ("model", "expected_str"),
        [
            (UserV123, "1.2.3"),
            (UserV200Beta1, "2.0.0-beta.1"),
            (UserV011Dev7, "0.1.1+dev.7"),
        ],
        ids=["simple", "prerelease", "dev"],
    )
    def test_parse_semver(
        self,
        migration_settings: MigrationSettings,
        model: type[types.VModel_co],
        expected_str: str,
    ) -> None:
        v = envelope_model(migration_settings, model)
        assert str(v) == expected_str

    @pytest.mark.parametrize(
        ("model", "expected_str"),
        [
            (UserV20250101, "2025-01-01"),
            (UserV20260228, "2026-02-28"),
            (UserV20260301_120530300Z, "2026-03-01"),
        ],
        ids=["without-time", "leap-year", "with-time"],
    )
    def test_parse_date(
        self,
        migration_settings: MigrationSettings,
        model: type[types.VModel_co],
        expected_str: str,
    ) -> None:
        v = envelope_model(migration_settings, model)
        assert str(v) == expected_str

    def test_invalid_semver_models(
        self, subtests: pytest.Subtests, migration_settings: MigrationSettings
    ) -> None:

        class InvalidBetaModel(BaseModel):
            version: Literal["beta.7"]

        class InvalidAlphaModel(BaseModel):
            version: Literal["0.0.0.alpha7"]

        for model in [InvalidBetaModel, InvalidAlphaModel]:
            with subtests.test(f"invalid-semver-version: {model.__name__}"):
                with pytest.raises(ValueError):
                    envelope_model(migration_settings, model)

    def test_invalid_date_models(
        self, subtests: pytest.Subtests, migration_settings: MigrationSettings
    ) -> None:

        class InvalidTimeModel(BaseModel):
            version: Literal["15:15:20.000Z"]

        for model in [InvalidTimeModel]:
            with subtests.test(f"invalid-date-version: {model.__name__}"):
                with pytest.raises(ValueError):
                    envelope_model(migration_settings, model)


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
        migration_settings: MigrationSettings,
        left: type[types.VModel_co],
        right: type[types.VModel_co],
        op: str,
    ) -> None:
        comp = getattr(operator, op)
        assert comp(
            envelope_model(migration_settings, left),
            envelope_model(migration_settings, right),
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
        migration_settings: MigrationSettings,
        left: type[types.VModel_co],
        right: type[types.VModel_co],
        op: str,
    ) -> None:
        with pytest.raises(TypeError):
            left_version = envelope_model(migration_settings, left)
            right_version = envelope_model(migration_settings, right)
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
        migration_settings: MigrationSettings,
        models: list[type[types.VModel_co]],
        expected: list[type[types.VModel_co]],
    ) -> None:
        versions = [envelope_model(migration_settings, model) for model in models]
        expected_versions = [
            envelope_model(migration_settings, model) for model in expected
        ]
        assert sorted(versions) == expected_versions

    @pytest.mark.parametrize(
        "models, expected",
        [
            ([UserV123, UserV011Dev7], 2),
            ([UserV20260228, UserV20250101, UserV20260301_120530300Z], 3),
        ],
    )
    def test_hashable(
        self,
        migration_settings: MigrationSettings,
        models: list[type[types.VModel_co]],
        expected: int,
    ) -> None:
        s = {envelope_model(migration_settings, model) for model in models}
        assert len(s) == expected


class TestRepresentation:
    @pytest.mark.parametrize(
        ("model", "expected_str", "expected_repr"),
        [
            (UserV123, "1.2.3", "ModelVersion[Version, UserV123](1.2.3)"),
            (
                UserV20251231,
                "2025-12-31",
                "ModelVersion[Date, UserV20251231](2025-12-31)",
            ),
            (
                UserV200Beta1,
                "2.0.0-beta.1",
                "ModelVersion[Version, UserV200Beta1](2.0.0-beta.1)",
            ),
        ],
        ids=["semver", "date", "prerelease"],
    )
    def test_str_repr(
        self,
        migration_settings: MigrationSettings,
        model: type[types.VModel_co],
        expected_str: str,
        expected_repr: str,
    ) -> None:
        v = envelope_model(migration_settings, model)
        assert str(v) == expected_str
        assert repr(v) == expected_repr

    @pytest.mark.parametrize(
        "model, expected_strategy",
        [(UserV123, Version), (UserV20251231, Date), (UserV200Beta1, Version)],
        ids=["semver", "date", "prerelease"],
    )
    def test_print_strategy(
        self,
        migration_settings: MigrationSettings,
        model: type[types.VModel_co],
        expected_strategy: str,
    ) -> None:
        v = envelope_model(migration_settings, model)
        assert v.strategy == expected_strategy
