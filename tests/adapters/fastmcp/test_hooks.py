"""Suite: the registry attaches observer hooks to every migration edge.

``ToolRegistry(hooks=...)`` fans a hook out to every registered edge during
``enrich``, so each migration step is observable without the customer wiring
per-edge hooks by hand.
"""

from __future__ import annotations

from fastmcp import FastMCP

from pyverge.core.hooks import MigrationHook


class _RecordingHook(MigrationHook):
    def __init__(self) -> None:
        self.steps: list[tuple[str, str]] = []

    def before_migrate(self, name, from_version, to_version, data) -> None:
        self.steps.append((str(name), str(from_version)))


class TestHookAttachment:
    def test_hook_attached_to_every_edge(
        self, weather_chain, configured_server
    ) -> None:
        hook = _RecordingHook()
        mcp = FastMCP("S")

        @mcp.tool(version="2.0.0")
        def search_weather(city: str, humidity: bool = False) -> dict:
            return {"city": city, "humidity": humidity}

        _, registry = configured_server(
            weather_chain,
            mcp,
            policies={"search_weather": "latest"},
            hooks=[hook],
        )

        handler = registry.delegate("search_weather", "1.0.0")
        assert handler is not None
        handler(city="Berlin")
        assert hook.steps, "the hook was not attached to the migration edge"
        assert hook.steps[0][0] == "search_weather"

    def test_no_hooks_by_default(self, weather_chain, configured_server) -> None:
        mcp = FastMCP("S")

        @mcp.tool(version="2.0.0")
        def search_weather(city: str, humidity: bool = False) -> dict:
            return {"city": city, "humidity": humidity}

        # No hooks passed → no error, no attachment.
        configured_server(weather_chain, mcp, policies={"search_weather": "latest"})
