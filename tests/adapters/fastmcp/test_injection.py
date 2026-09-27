"""Suite: injected parameters are excluded from the reflected contract.

A dependency-injected parameter is wiring, not payload. The adapter recognizes
the markers (dependency-injector ``Provide`` and FastMCP ``Depends``) and drops
them before reflecting the tool's signature into a model, so the tool needs no
signature rewrite.
"""

from __future__ import annotations

from fastmcp import FastMCP

from pyverge.adapters.fastmcp import default_injection_detector, injected_names


class _Service:
    def value(self) -> int:
        return 7


def _provide_default():
    """Lazy import so the test does not hard-depend on the library."""
    from dependency_injector.wiring import Provide  # noqa: PLC0415

    return Provide["service"]


class TestInjectionDetection:
    def test_detects_provide_marker(self) -> None:
        def tool(city: str, service=_provide_default()):
            return city

        assert injected_names(tool) == {"service"}

    def test_plain_defaults_are_not_injected(self) -> None:
        def tool(city: str, units: str = "celsius"):
            return city

        assert injected_names(tool) == set()

    def test_detects_depends_marker(self) -> None:
        from uncalled_for import Depends  # noqa: PLC0415

        def tool(city: str, service=Depends(_Service)):
            return city

        assert injected_names(tool) == {"service"}

    def test_custom_detector_overrides(self) -> None:
        def tool(city: str, marker: int = -1):
            return city

        detector = lambda p: p.name == "marker"  # noqa: E731
        assert injected_names(tool, detector) == {"marker"}

    def test_detector_handles_builtin_without_signature(self) -> None:
        assert injected_names(len, default_injection_detector()) == set()


class TestReflectedSchemaExcludesInjected:
    def test_injected_param_absent_from_registered_anchor(
        self, weather_chain, configured_server
    ) -> None:
        """The reflected anchor model must not carry the injected parameter."""
        mcp = FastMCP("S")

        @mcp.tool(version="2.0.0")
        def search_weather(
            city: str, humidity: bool = False, service=_provide_default()
        ):
            return {"city": city, "humidity": humidity}

        _, registry = configured_server(
            weather_chain, mcp, policies={"search_weather": "latest"}
        )
        # Reconcile passed, meaning the reflected surface ignored `service`.
        assert registry.delegate("search_weather", "2.0.0") is not None

    def test_signature_helper_reports_injected(self) -> None:
        def tool(city: str, service=_provide_default()):
            return city

        names = injected_names(tool)
        assert "service" in names
        assert "city" not in names
