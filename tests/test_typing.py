"""Pytest wrapper around ``ty check`` for static typing regression tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TYPING_DIR = Path(__file__).parent / "typing"


def test_typing_discriminated_union() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ty", "check", str(TYPING_DIR)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        "ty check failed for tests/typing\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
