"""FastMCP integration adapter.

The FastMCP adapter plugs pyverge into a FastMCP tool server. It is the first
*adapter* behind pyverge's ports: the customer hands their manager to
:class:`ToolRegistry` (a standard FastMCP ``lifespan`` hook), and the adapter
reflects the server through ``list_tools`` under a deterministic flow:

1. the physical versioned tools are the anchors — the adapter reflects each
   tool's signature into a model and materializes it into the manager,
2. nested versioned models *used* by a tool's arguments must be registered;
   versions with no physical declaration are reconstructed from the anchor
   when the customer registers their migrations.

One manager per source: the adapter binds exactly one bounded context, so there
is no manager routing — a manager owns one complete version graph. The adapter
precomputes convergence paths and materializes virtual tools for every
registered version. Injected parameters (dependency-injector ``Provide``,
FastMCP ``Depends``) are recognized and excluded from the contract by
:mod:`pyverge.adapters.fastmcp.injection`. Per-component reflection — a single
tool, prompt or resource plus a pyverge model adapter into a compliant model —
lives in :mod:`pyverge.adapters.fastmcp.reflection`. A per-call
:class:`ConvergeMiddleware` converges arguments — nested versioned models
included — to the policy target before the handler runs. pyverge core and ports
never import FastMCP.
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
from .tools import hide_injected, make_tool

__all__ = [
    "ComponentReflection",
    "ConvergeMiddleware",
    "Converger",
    "InjectionDetector",
    "PromptReflection",
    "ResourceReflection",
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
