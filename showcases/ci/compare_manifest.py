"""Compare a generated manifest with the checked-in snapshot."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

IGNORED_METADATA = {"generated_at"}


def _canonical(path: Path) -> dict[str, Any]:
    envelope = json.loads(path.read_text())
    metadata = envelope["graph"]["metadata"]
    for key in IGNORED_METADATA:
        metadata.pop(key, None)
    return envelope


def main() -> int:
    current = _canonical(Path("target/pyverge-manifest.json"))
    baseline = _canonical(Path("manifest.json"))
    if current != baseline:
        print("manifest divergence detected")
        print(json.dumps(current, indent=2, sort_keys=True))
        return 1
    print("manifest snapshot matches")
    return 0


if __name__ == "__main__":
    sys.exit(main())
