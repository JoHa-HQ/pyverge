# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared case value for the FastMCP adapter suites."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Case:
    """A physical tool plus the call that must converge through it.

    Parametrize the ``case`` fixture (indirectly) with a :class:`Case`; the
    ``app`` fixture materializes its tool and the test drives ``client``.
    ``call_version`` is negotiated natively (FastMCP's ``version=``).
    """

    id: str
    kind: str
    handler: Callable[..., Any]
    version: str | None = None
    policies: dict[str, str] = field(default_factory=dict)
    args: dict[str, Any] = field(default_factory=dict)
    expected: dict[str, Any] = field(default_factory=dict)
    call_version: str | None = None


def _source_handler(name: str, age: int | None = None) -> dict[str, Any]:
    return {"name": name, "age": age}


SOURCE_CASE = Case(
    id="source",
    kind="User",
    handler=_source_handler,
    version="2.0.0",
    args={"name": "A"},
    expected={"name": "A", "age": None},
    call_version="2.0.0",
)


__all__ = ["SOURCE_CASE", "Case"]
