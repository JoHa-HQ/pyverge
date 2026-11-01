# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""FastMCP SourcePort adapter tests."""

from __future__ import annotations

import asyncio


def test_source_registers_default_tool_models(manager, source) -> None:
    report = asyncio.run(manager.areflect(source))

    assert report.registered_models == 1
    assert [str(version) for version in manager._default_engine.registry.versions] == [
        "test:User@2.0.0"
    ]
