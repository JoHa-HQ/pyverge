"""FastMCP integration adapter.

Plugs pyverge into a FastMCP tool server. The customer hands their manager to
:class:`ToolRegistry` (a standard FastMCP ``lifespan`` hook); the adapter
reflects the server through ``list_tools``, registers each versioned tool's
signature as an anchor, reconciles it against the graph and materializes virtual
tools for the remaining versions. A per-call :class:`ConvergeMiddleware`
converges arguments to the policy target before the handler runs.

The adapter is a composition over one :class:`~pyverge.manager.Manager` and the
FastMCP server: endpoint/convergence/reflection helpers here are adapter-local
representations (they reference both the manager and its model adapter), not a
neutral port. pyverge core and ports never import FastMCP.
"""

from .converger import Converger
from .discovery import ToolDiscovery
from .injection import (
    InjectionDetector,
    default_injection_detector,
    injected_names,
    marker_detector,
    never_injected,
)
from .middleware import ConvergeMiddleware
from .reflection import (
    ComponentReflection,
    PromptReflection,
    ResourceReflection,
    ToolReflection,
)
from .registry import ToolRegistry
from .schema import SchemaReflection
from .tools import hide_injected, make_tool

__all__ = [
    "ComponentReflection",
    "ConvergeMiddleware",
    "Converger",
    "InjectionDetector",
    "PromptReflection",
    "ResourceReflection",
    "SchemaReflection",
    "ToolDiscovery",
    "ToolReflection",
    "ToolRegistry",
    "default_injection_detector",
    "hide_injected",
    "injected_names",
    "make_tool",
    "marker_detector",
    "never_injected",
]
