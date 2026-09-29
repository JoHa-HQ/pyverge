"""FastMCP integration adapter.

Plugs pyverge into a FastMCP server. The customer hands their manager and a set
of reflection providers to :class:`ToolDiscovery`, which indexes the versioned
primitives, registers each as an anchor (validating it against the graph), and
materializes the virtual surface. The customer drives the lifecycle
(search → register → enrich). Version negotiation is FastMCP's own: a call's
``version=`` routes to the matching virtual primitive.

The adapter is a composition over one :class:`~pyverge.manager.Manager` and the
FastMCP server: discovery/convergence/reflection helpers here are adapter-local
representations (they reference both the manager and its model adapter), not a
neutral port. pyverge core and ports never import FastMCP.
"""

from .converge import Converger
from .discovery import ToolDiscovery
from .injection import (
    InjectionDetector,
    default_injection_detector,
    injected_names,
    marker_detector,
    never_injected,
)
from .reflection import (
    ComponentReflection,
    PromptReflection,
    ReflectedNode,
    ResourceReflection,
    ToolReflection,
)
from .tools import hide_injected, prompt, resource, tool

__all__ = [
    "ComponentReflection",
    "Converger",
    "InjectionDetector",
    "PromptReflection",
    "ReflectedNode",
    "ResourceReflection",
    "ToolDiscovery",
    "ToolReflection",
    "default_injection_detector",
    "hide_injected",
    "injected_names",
    "marker_detector",
    "never_injected",
    "prompt",
    "resource",
    "tool",
]
