"""JSON Schema model provider adapter.

:class:`JsonSchemaModelAdapter` converts a JSON Schema document (a plain
dict) into a Pydantic model via ``datamodel-code-generator`` and registers
that model with the engine.
"""

from .adapter import JsonSchemaModelAdapter

__all__ = ["JsonSchemaModelAdapter"]
