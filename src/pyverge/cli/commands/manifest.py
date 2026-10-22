"""Export the migration graph as a JGF-enveloped manifest."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer

from pyverge import __version__
from pyverge.core.types import MigrationFunc
from pyverge.providers import JsonataTransform

from .._helpers import write_json_file
from ..config import ConfigError, resolve_manager
from ._shared import ManagerOption, dump_json

MANIFEST_VERSION = "1.0"


def _hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _migration_identity(func: MigrationFunc) -> dict[str, Any]:
    """Serialize a migration by identity, never by callable body."""
    if isinstance(func, JsonataTransform):
        return {"strategy": "jsonata", "expression": func.expression}
    ops = getattr(func, "patch", None)
    if isinstance(ops, list):
        return {"strategy": "jsonpatch", "ops": ops}
    return {
        "strategy": "callable",
        "callable": getattr(func, "__qualname__", type(func).__name__),
        "module": getattr(func, "__module__", None),
    }


def _semantic_manifest(envelope: dict[str, Any]) -> dict[str, Any]:
    """Return only graph content, excluding volatile metadata."""
    graph = envelope["graph"]
    return {
        "manifest_version": graph["metadata"].get("manifest_version"),
        "nodes": graph["nodes"],
        "edges": graph["edges"],
    }


def _diff_summary(
    current: dict[str, Any],
    baseline: dict[str, Any],
) -> list[str]:
    current_nodes = set(current["nodes"])
    baseline_nodes = set(baseline["nodes"])
    current_edges = {edge["id"] for edge in current["edges"]}
    baseline_edges = {edge["id"] for edge in baseline["edges"]}
    issues: list[str] = []
    for label, changed in (
        ("node added", current_nodes - baseline_nodes),
        ("node removed", baseline_nodes - current_nodes),
        ("edge added", current_edges - baseline_edges),
        ("edge removed", baseline_edges - current_edges),
    ):
        if changed:
            issues.append(f"{label}: {', '.join(sorted(changed))}")
    return issues


def build_manifest(manager: Any, *, manager_spec: str) -> dict[str, Any]:
    """Build a JGF v2 envelope for the manager's registry graph."""
    registry = manager.registry
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    for kind in registry.entities:
        for version in registry.kind_versions(kind):
            node_id = f"{kind}@{version.version[1]}"
            references = [
                f"{ref_kind}@{ref_version}"
                for ref_kind, ref_version in sorted(version.references)
            ]
            metadata = {
                "kind": kind,
                "version": str(version.version[1]),
                "model": getattr(version.model, "__name__", None),
                "fields": sorted(version.fields),
                "references": references,
            }
            metadata["schema_hash"] = _hash(metadata)
            nodes[node_id] = {
                "label": node_id,
                "metadata": metadata,
            }

    for kind in registry.kinds:
        for edge in registry.migrations(kind):
            source = f"{kind}@{edge.source.version[1]}"
            target = f"{kind}@{edge.target.version[1]}"
            migration = _migration_identity(edge.func)
            metadata = {
                "kind": kind,
                "from": str(edge.source.version[1]),
                "to": str(edge.target.version[1]),
                "backward_compatible": edge.diff.is_backward_compatible,
                **migration,
            }
            metadata["migration_hash"] = _hash(metadata)
            edges.append(
                {
                    "id": f"{source}->{target}",
                    "source": source,
                    "target": target,
                    "relation": "migration",
                    "directed": True,
                    "metadata": metadata,
                }
            )

    edges.sort(key=lambda item: item["id"])
    graph: dict[str, Any] = {
        "id": "pyverge",
        "label": "pyverge migration graph",
        "type": "directed",
        "directed": True,
        "metadata": {
            "manifest_version": MANIFEST_VERSION,
            "pyverge_version": __version__,
            "manager": manager_spec,
        },
        "nodes": nodes,
        "edges": edges,
    }
    content_hash = _hash(graph)
    graph["metadata"]["generated_at"] = datetime.now(UTC).isoformat()
    graph["metadata"]["content_hash"] = content_hash
    return {"graph": graph}


def manifest(
    manager: ManagerOption,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write manifest file")
    ] = None,
    baseline: Annotated[
        Path | None,
        typer.Option("--baseline", help="Compare against a manifest snapshot"),
    ] = None,
) -> None:
    """Export the graph as a JGF v2 manifest snapshot."""
    try:
        mgr = resolve_manager(manager)
        envelope = build_manifest(mgr, manager_spec=manager)
        if output is not None:
            write_json_file(output, envelope)
        else:
            dump_json(envelope)

        if baseline is not None:
            base_envelope = json.loads(baseline.read_text())
            current = _semantic_manifest(envelope)
            expected = _semantic_manifest(base_envelope)
            if current != expected:
                typer.secho("Manifest divergence detected", fg=typer.colors.RED)
                for issue in _diff_summary(current, expected):
                    typer.echo(f"  - {issue}")
                raise typer.Exit(1)
            typer.secho("Manifest snapshot matches", fg=typer.colors.GREEN)
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1) from exc
