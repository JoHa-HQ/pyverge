# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import pyverge
from pyverge.core.engine import Engine
from pyverge.runtime.manager import Manager

SOURCE = Path(__file__).resolve().parents[1] / "src" / "pyverge"

GROUPS = {
    "core": ("core", "schemas", "migrations", "discovery"),
    "runtime": ("runtime",),
    "integration": ("adapters",),
    "tooling": ("cli", "settings"),
}

FORBIDDEN = {
    "core": ("runtime", "adapters", "cli", "settings"),
    "runtime": ("adapters", "cli"),
    "integration": ("cli",),
}


def _absolute_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def _paths(group: str) -> list[Path]:
    return [
        path
        for directory in GROUPS[group]
        for path in (SOURCE / directory).rglob("*.py")
    ]


@pytest.mark.parametrize(("group", "forbidden"), FORBIDDEN.items())
def test_no_forbidden_cross_group_imports(
    group: str,
    forbidden: tuple[str, ...],
) -> None:
    violations: list[str] = []
    for path in _paths(group):
        for module in _absolute_imports(path):
            for target in forbidden:
                if module == f"pyverge.{target}" or module.startswith(
                    f"pyverge.{target}."
                ):
                    violations.append(f"{path.relative_to(SOURCE)} -> {module}")
    assert violations == []


def test_public_package_imports() -> None:
    assert pyverge.Engine is Engine
    assert pyverge.Manager is Manager
