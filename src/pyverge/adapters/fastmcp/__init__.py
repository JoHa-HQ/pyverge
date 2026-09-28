"""FastMCP integration adapter.

Plugs pyverge into a FastMCP tool server. The customer hands their manager to
:class:`ToolRegistry` (a standard FastMCP ``lifespan`` hook); the adapter
reflects the server through ``list_tools``, registers each versioned tool's
signature as an anchor, reconciles it against the graph and materializes virtual
tools for the remaining versions. A per-call :class:`ConvergeMiddleware`
converges arguments to the policy target before the handler runs.

The framework-agnostic work lives in :mod:`pyverge.serving`; this package is the
FastMCP context wiring only. pyverge core and ports never import FastMCP.
"""

from pyverge.serving import (
    Converger,
    InjectionDetector,
    SchemaReflection,
    ServingContract,
    default_injection_detector,
    injected_names,
    marker_detector,
    never_injected,
)

from .discovery import ToolDiscovery
from .middleware import ConvergeMiddleware
from .reflection import (
    ComponentReflection,
    PromptReflection,
    ResourceReflection,
    ToolReflection,
)
from .registry import ToolRegistry
from .tools import hide_injected, make_tool

__all__ = [
    "ComponentReflection",
    "ConvergeMiddleware",
    "Converger",
    "InjectionDetector",
    "PromptReflection",
    "ResourceReflection",
    "SchemaReflection",
    "ServingContract",
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
