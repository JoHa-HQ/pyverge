"""Utilities for inspecting Pydantic RootModel types."""

from typing import Any

from pydantic import BaseModel, RootModel


class TypeInspector:
    """Utilities for RootModel detection and annotation access."""

    @staticmethod
    def is_root_model(model_class: type[BaseModel]) -> bool:
        """Check if a model class is a RootModel."""
        return issubclass(model_class, RootModel)

    @staticmethod
    def get_root_annotation(model_class: type[BaseModel]) -> Any:
        """Get the root type annotation from a RootModel."""
        if not TypeInspector.is_root_model(model_class):
            raise ValueError(f"{model_class.__name__} is not a RootModel")

        root_field = model_class.model_fields.get("root")
        if root_field is None:
            raise ValueError(f"{model_class.__name__} has no root field")

        return root_field.annotation
