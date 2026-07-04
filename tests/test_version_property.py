"""Tests for ModelVersion — parsing, comparison, hashing."""

from __future__ import annotations

import pytest

from pydantic_migrator.migration.versioning import ModelVersion


class TestParse:
    @pytest.mark.parametrize(
        ("version_str", "kind", "expected_str"),
        [
            ("1.2.3", "semver", "1.2.3"),
            ("2.0.0-beta.1", "semver", "2.0.0-beta.1"),
            ("0.1.1-dev.7", "semver", "0.1.1-dev.7"),
            ("2024-06-01", "date", "2024-06-01"),
        ],
        ids=["simple", "prerelease", "dev", "date"],
    )
    def test_parse(self, version_str: str, kind: str, expected_str: str) -> None:
        v = ModelVersion.parse(version_str)
        assert v.kind == kind
        assert str(v) == expected_str

    def test_date_with_time(self) -> None:
        v = ModelVersion.parse("2025-03-15T10:30:00")
        assert v.kind == "date"
        assert "2025-03-15" in str(v)

    def test_idempotent(self) -> None:
        v = ModelVersion.parse("1.0.0")
        assert ModelVersion.parse(v) is v

    @pytest.mark.parametrize(
        "invalid",
        ["not-a-version", "", "abc123"],
        ids=["garbage", "empty", "nonsense"],
    )
    def test_invalid(self, invalid: str) -> None:
        with pytest.raises(ValueError, match="Cannot parse"):
            ModelVersion.parse(invalid)


class TestComparison:
    @pytest.mark.parametrize(
        ("left", "right"),
        [
            ("1.0.0", "2.0.0"),
            ("1.0.0-alpha", "1.0.0"),
            ("2024-01-01", "2025-01-01"),
        ],
        ids=["semver", "prerelease", "date"],
    )
    def test_less_than(self, left: str, right: str) -> None:
        assert ModelVersion.parse(left) < ModelVersion.parse(right)

    def test_equal(self) -> None:
        assert ModelVersion.parse("1.0.0") == ModelVersion.parse("1.0.0")

    def test_semver_vs_date(self) -> None:
        with pytest.raises(TypeError):
            ModelVersion.parse("1.0.0") < ModelVersion.parse("2024-06-01")  # type: ignore[reportUnusedExpression]

    def test_sortable(self) -> None:
        versions = [
            ModelVersion.parse("2.0.0"),
            ModelVersion.parse("1.0.0"),
            ModelVersion.parse("1.5.0"),
        ]
        assert sorted(versions) == [
            ModelVersion.parse("1.0.0"),
            ModelVersion.parse("1.5.0"),
            ModelVersion.parse("2.0.0"),
        ]


class TestHashing:
    def test_equal_versions_hash_equal(self) -> None:
        assert hash(ModelVersion.parse("1.0.0")) == hash(ModelVersion.parse("1.0.0"))

    def test_different_versions_hash_different(self) -> None:
        assert hash(ModelVersion.parse("1.0.0")) != hash(ModelVersion.parse("2.0.0"))

    def test_usable_in_set(self) -> None:
        s = {
            ModelVersion.parse("1.0.0"),
            ModelVersion.parse("2.0.0"),
            ModelVersion.parse("1.0.0"),
        }
        assert len(s) == 2


class TestStringRepresentation:
    @pytest.mark.parametrize(
        ("version_str", "expected"),
        [
            ("1.2.3", "1.2.3"),
            ("2024-06-01", "2024-06-01"),
            ("2.0.0-beta.1", "2.0.0-beta.1"),
        ],
        ids=["semver", "date", "prerelease"],
    )
    def test_str(self, version_str: str, expected: str) -> None:
        assert str(ModelVersion.parse(version_str)) == expected

    def test_repr(self) -> None:
        assert repr(ModelVersion.parse("1.2.3")) == 'ModelVersion("1.2.3")'
