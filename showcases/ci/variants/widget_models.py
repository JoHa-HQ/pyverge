"""Models used only when hydrating the key-only Widget graph."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class WidgetV1(BaseModel):
    kind: Literal["Widget"] = "Widget"
    version: Literal["1.0.0"] = "1.0.0"
    name: str


class WidgetV2(BaseModel):
    kind: Literal["Widget"] = "Widget"
    version: Literal["2.0.0"] = "2.0.0"
    name: str
    size: int = 0
