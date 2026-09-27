"""Container wiring tests.

These assert the composition root builds the graph correctly and that the
settings tree drives construction — without touching a server or a collector.
"""

from __future__ import annotations

from fastmcp_demo.container import build_container
from fastmcp_demo.settings import DemoSettings, GraphSettings, TelemetrySettings


def _settings(**graph_overrides) -> DemoSettings:
    return DemoSettings(
        graph=GraphSettings(**graph_overrides),
        telemetry=TelemetrySettings(enabled=False),
    )


class TestContainer:
    def test_service_is_singleton(self, container) -> None:
        assert container.demo_service() is container.demo_service()

    def test_manager_is_singleton(self, container) -> None:
        assert container.manager() is container.manager()

    def test_settings_override_is_honored(self) -> None:
        container = build_container(_settings(policy="earliest"))
        assert container.settings().graph.policy == "earliest"

    def test_tracer_disabled_in_tests(self, container) -> None:
        assert container.tracer() is None

    def test_registry_and_server_share_the_manager(self, container) -> None:
        service = container.demo_service()
        assert service.registry is container.registry()
        assert service.server is container.server()


class TestGraphRegistration:
    def test_all_versions_registered(self, manager) -> None:
        versions = [
            str(node.version[1]) for node in manager.list_versions("search_weather")
        ]
        assert versions == ["1.0.0", "2.0.0", "3.0.0"]

    def test_older_models_were_reconstructed(self, manager) -> None:
        """Only v3 is registered concretely; v1/v2 are rebuilt from the anchor."""
        v1 = manager.get("search_weather", "1.0.0")
        assert v1.model is not None
        assert "humidity" not in v1.model.model_fields
        assert "wind" not in v1.model.model_fields
