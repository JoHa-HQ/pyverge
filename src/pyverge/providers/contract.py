"""Compatibility shim: provider type surface now lives in
:mod:`pyverge.providers.types`.
"""

from __future__ import annotations

from .types import (
    Container_co,
    ModelAdapter,
    ProviderBase,
    ProviderBase_co,
    TContainer,
    VModel,
    VModel_co,
    VSource_co,
    VTarget_co,
)

__all__ = [
    "Container_co",
    "ModelAdapter",
    "ProviderBase",
    "ProviderBase_co",
    "TContainer",
    "VModel",
    "VModel_co",
    "VSource_co",
    "VTarget_co",
]
