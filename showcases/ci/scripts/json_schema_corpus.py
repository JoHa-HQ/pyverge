"""Run a supported subset of the official JSON Schema Test Suite.

This is adapter conformance, not full JSON Schema validation. The PyVerge JSON
Schema adapter materializes object models; it is not a general-purpose validator.
The suite is filtered to object schemas with simple identifier-named properties
and primitive field types.

Usage:
    python showcases/ci/scripts/json_schema_corpus.py /path/to/JSON-Schema-Test-Suite
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from pydantic import ValidationError

from pyverge.schemas import JsonSchemaModelAdapter, ModelCodec

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SUPPORTED_TYPES = {"string", "integer", "number", "boolean"}
_FILES = ("properties.json", "required.json")


def _supported(group: dict) -> bool:
    schema = group["schema"]
    if schema.get("type", "object") != "object":
        return False
    if set(schema) - {"$schema", "type", "properties", "required"}:
        return False
    props = schema.get("properties", {})
    names = [*props, *schema.get("required", ())]
    if any(
        not _IDENTIFIER.fullmatch(name)
        or name.startswith("_")
        or name in {"constructor", "toString"}
        for name in names
    ):
        return False
    for definition in props.values():
        if not isinstance(definition, dict):
            return False
        if definition and definition.get("type") not in _SUPPORTED_TYPES:
            return False
    return True


def _with_identity(schema: dict) -> dict:
    properties = dict(schema.get("properties", {}))
    for name in schema.get("required", ()):
        properties.setdefault(name, {})
    properties.update(
        {
            "kind": {"type": "string", "default": "Corpus"},
            "version": {"type": "string", "default": "1.0.0"},
        }
    )
    required = list(dict.fromkeys([*schema.get("required", ()), "kind", "version"]))
    return {**schema, "properties": properties, "required": required}


def main(suite_root: str) -> int:  # noqa: C901
    root = Path(suite_root) / "tests" / "draft2020-12"
    adapter = JsonSchemaModelAdapter(
        codec=ModelCodec(
            namespace="",
            version_property="version",
            kind_property="kind",
        )
    )
    groups = cases = skipped = 0
    failures: list[str] = []

    for filename in _FILES:
        for group in json.loads((root / filename).read_text()):
            if not _supported(group):
                continue
            groups += 1
            model = adapter.to_pydantic(
                _with_identity(group["schema"]),
                class_name="Corpus",
            )
            for case in group["tests"]:
                data = case["data"]
                if not isinstance(data, dict):
                    skipped += 1
                    continue
                cases += 1
                payload = {**data, "kind": "Corpus", "version": "1.0.0"}
                try:
                    model.model_validate(payload)
                except ValidationError:
                    valid = False
                else:
                    valid = True
                if valid is not case["valid"]:
                    failures.append(
                        f"{filename}: {group['description']} / "
                        f"{case['description']} (expected valid={case['valid']})"
                    )

    print(
        f"JSON Schema corpus: groups={groups} cases={cases} "
        f"skipped_non_objects={skipped} failures={len(failures)}"
    )
    for failure in failures:
        print(f"  FAIL {failure}")
    if groups < 3:  # noqa: PLR2004
        print("Corpus filter is too narrow; expected at least 3 supported groups.")
        return 1
    return 1 if failures else 0


if __name__ == "__main__":
    default_suite = "JSON-Schema-Test-Suite"
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else default_suite))
