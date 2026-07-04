"""Tests for version property validation feature."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, Field, create_model

from pydantic_migrator import ModelManager, ModelVersion
from pydantic_migrator.models import ManagerSettings


class TestVersionPropertyValidation:
    """Test that version property is validated at registration time."""

    @pytest.mark.parametrize(
        "field_name,version,expected",
        [
            ("version", "1.0.0", "1.0.0"),
            ("schema_version", "2.1.0", "2.1.0"),
            ("model_version", "0.1.1", "0.1.1"),
            ("v", "3.0.0-beta.1", "3.0.0-beta.1"),
            ("version", "0.1.1.dev7", "0.1.1.dev7"),
        ],
        ids=[
            "default-version-field",
            "custom-schema-version",
            "model-version-field",
            "short-v-field",
            "dev-version",
        ],
    )
    def test_version_property_with_different_names(
        self, field_name: str, version: str, expected: str
    ) -> None:
        """Test that version field is validated with different field names."""
        manager = ModelManager["TestModel"](
            ManagerSettings(version_property=field_name)
        )

        # Build model with the dynamic version field name
        namespace = {"name": (str, ...), field_name: (str, Field(default=expected))}
        TestModel = create_model("TestModel", **namespace)

        @manager.model(version)
        class _TestModel(TestModel):  # type: ignore[no-redef]
            pass

        instance = _TestModel(name="test")
        assert getattr(instance, field_name) == expected

    def test_version_property_in_model_fields(self) -> None:
        """Test that version property is declared in Pydantic model fields."""
        manager = ModelManager["TestModel"](ManagerSettings(version_property="version"))

        @manager.model("1.0.0")
        class TestModel(BaseModel):
            name: str
            version: str = "1.0.0"

        assert "version" in TestModel.model_fields
        assert TestModel.model_fields["version"].default == "1.0.0"

    def test_version_property_serialized(self, snapshot) -> None:
        """Test that version property is included in JSON serialization."""
        manager = ModelManager["TestModel"](ManagerSettings(version_property="version"))

        @manager.model("1.0.0")
        class TestModel(BaseModel):
            name: str
            version: str = "1.0.0"

        instance = TestModel(name="Alice")
        assert instance.model_dump() == snapshot()

    def test_version_property_default(self) -> None:
        """Test that version field has the correct default from registration."""
        manager = ModelManager["TestModel"](ManagerSettings(version_property="version"))

        @manager.model("1.0.0")
        class TestModel(BaseModel):
            name: str
            version: str = "1.0.0"

        instance = TestModel(name="test")
        assert instance.version == "1.0.0"

    def test_version_property_class_and_instance_access(self) -> None:
        """Test that version is accessible from both class and instance."""
        manager = ModelManager["TestModel"](ManagerSettings(version_property="version"))

        @manager.model("1.0.0")
        class TestModel(BaseModel):
            name: str
            version: str = "1.0.0"

        # Access via class (model_fields default)
        assert TestModel.model_fields["version"].default == "1.0.0"

        # Access via instance
        instance = TestModel(name="test")
        assert instance.version == "1.0.0"

    def test_version_property_multiple_versions(self) -> None:
        """Test that each version gets the correct version field default."""
        manager = ModelManager["TestModel"](ManagerSettings(version_property="version"))

        @manager.model("1.0.0")
        class TestV1(BaseModel):
            name: str
            version: str = "1.0.0"

        @manager.model("2.0.0")
        class TestV2(BaseModel):
            name: str
            email: str
            version: str = "2.0.0"

        @manager.model("2.1.0-beta")
        class TestV2_1_Beta(BaseModel):
            name: str
            email: str
            age: int | None = None
            version: str = "2.1.0-beta"

        assert TestV1.model_fields["version"].default == "1.0.0"
        assert TestV2.model_fields["version"].default == "2.0.0"
        assert TestV2_1_Beta.model_fields["version"].default == "2.1.0-beta"

        instance_v1 = TestV1(name="test1")
        instance_v2 = TestV2(name="test2", email="test2@example.com")
        instance_v2_1_beta = TestV2_1_Beta(
            name="test3", email="test3@example.com", age=30
        )

        assert instance_v1.version == "1.0.0"
        assert instance_v2.version == "2.0.0"
        assert instance_v2_1_beta.version == "2.1.0-beta"

    def test_version_property_disabled(self) -> None:
        """Test that version field not validated when disabled."""
        manager = ModelManager["TestModel"](ManagerSettings(version_property=None))

        @manager.model("1.0.0")
        class TestModel(BaseModel):
            name: str

        assert "version" not in TestModel.model_fields
        instance = TestModel(name="test")
        assert not hasattr(instance, "version")

    def test_version_property_default_name(self) -> None:
        """Test that default version field name matches ManagerSettings default."""
        manager = ModelManager["TestModel"]()

        @manager.model("1.0.0")
        class TestModel(BaseModel):
            name: str
            version: str = "1.0.0"

        assert "version" in TestModel.model_fields
        assert TestModel.model_fields["version"].default == "1.0.0"

    def test_version_property_with_model_version_type(self) -> None:
        """Test that version field works with ModelVersion type parameter."""
        manager = ModelManager["TestModel"](ManagerSettings(version_property="version"))
        version_obj = ModelVersion.parse("1.2.3")

        @manager.model(version_obj)
        class TestModel(BaseModel):
            name: str
            version: str = "1.2.3"

        assert TestModel.model_fields["version"].default == "1.2.3"
        instance = TestModel(name="test")
        assert instance.version == "1.2.3"
