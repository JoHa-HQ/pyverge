"""Tests for the framework-agnostic serving core (:mod:`pyverge.serving`).

The FastMCP adapter tests exercise these through FastMCP; this module tests the
core directly, so it stays host-independent.
"""

from __future__ import annotations

import inspect

from pyverge.ports import JsonSchemaModelAdapter
from pyverge.serving import (
    SchemaReflection,
    default_injection_detector,
    injected_names,
    marker_detector,
    never_injected,
)
from pyverge.serving.contract import nested_kinds

ADAPTER = JsonSchemaModelAdapter()


class _Svc:
    def value(self) -> int:
        return 1


def _provide_default():
    from dependency_injector.wiring import Provide  # noqa: PLC0415

    return Provide["svc"]


class TestInjection:
    def test_never_injected_flags_nothing(self) -> None:
        assert (
            never_injected(
                inspect.Parameter("x", inspect.Parameter.POSITIONAL_OR_KEYWORD)
            )
            is False
        )

    def test_marker_detector(self) -> None:
        class Marker:
            pass

        detect = marker_detector(Marker)
        hit = inspect.Parameter(
            "m", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=Marker()
        )
        miss = inspect.Parameter(
            "m", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=1
        )
        assert detect(hit) is True
        assert detect(miss) is False

    def test_injected_names_detects_provide(self) -> None:
        def tool(city: str, svc=_provide_default()):
            return city

        assert injected_names(tool) == {"svc"}

    def test_injected_names_plain_signature(self) -> None:
        def tool(city: str, units: str = "celsius"):
            return city

        assert injected_names(tool) == set()

    def test_injected_names_handles_no_signature(self) -> None:
        assert injected_names(len, default_injection_detector()) == set()


class TestSchemaReflection:
    def test_drops_injected_then_injects_identity(self) -> None:
        reflection = SchemaReflection(
            ADAPTER,
            kind="weather",
            version="1.0.0",
            schema={"properties": {"city": {"type": "string"}, "svc": {}}},
            injected=frozenset({"svc"}),
        )
        props = reflection.compliant()["properties"]
        assert "svc" not in props
        assert props["kind"] == {"type": "string", "default": "weather"}
        assert props["version"] == {"type": "string", "default": "1.0.0"}

    def test_removes_injected_from_required(self) -> None:
        reflection = SchemaReflection(
            ADAPTER,
            kind="k",
            version="1.0.0",
            schema={
                "properties": {"city": {"type": "string"}},
                "required": ["city", "svc"],
            },
            injected=frozenset({"svc"}),
        )
        assert reflection.compliant()["required"] == ["city"]

    def test_versionable_wraps_through_adapter(self) -> None:
        reflection = SchemaReflection(
            ADAPTER,
            kind="weather",
            version="1.0.0",
            schema={"properties": {"city": {"type": "string"}}},
        )
        node = reflection.versionable()
        assert set(node.model.model_fields) == {"city", "kind", "version"}


class TestContractHelpers:
    def test_nested_kinds_finds_versioned_objects(self) -> None:
        schema = {
            "properties": {
                "place": {
                    "type": "object",
                    "properties": {
                        "kind": {"default": "location"},
                        "version": {"default": "1.0.0"},
                    },
                },
                "name": {"type": "string"},
            }
        }
        assert nested_kinds(schema) == ["location"]

    def test_nested_kinds_ignores_plain_objects(self) -> None:
        schema = {"properties": {"place": {"type": "object", "properties": {"x": {}}}}}
        assert nested_kinds(schema) == []
