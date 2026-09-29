"""FastMCP + OpenTelemetry showcase, as a layered, DI-wired application.

The package is split into four layers:

* :mod:`fastmcp_demo.settings` — pydantic-settings configuration.
* :mod:`fastmcp_demo.domain` — the version graph: kinds, versions, migration
  specs and the ``Manager`` factory. No FastMCP, no I/O.
* :mod:`fastmcp_demo.ports` — narrow protocols the application depends on.
* :mod:`fastmcp_demo.adapters` — concrete adapters: the FastMCP server and the
  OpenTelemetry tracing provider.
* :mod:`fastmcp_demo.application` — the ``DemoService`` use case orchestrating
  the lifecycle.
* :mod:`fastmcp_demo.container` — the dependency-injector composition root.

Run it with::

    PYTHONPATH=showcases/fastmcp/src uv run python -m fastmcp_demo
"""

__all__: list[str] = []
