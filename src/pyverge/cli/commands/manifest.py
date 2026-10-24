"""Export the migration graph as a JGF-enveloped manifest."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, cast

import typer

from pyverge import __version__
from pyverge.convergence.catalog.ports import GraphCatalog
from pyverge.export import (
    JgfExporter,
    ManifestDiff,
    ManifestExporter,
    ManifestSpec,
    ManifestVersion,
)
from pyverge.versioning import default_content_hasher

from .._helpers import write_json_file
from ..config import ConfigError, resolve_manager
from ._shared import ManagerOption, dump_json

MANIFEST_VERSION = "1.0"


def manifest(
    manager: ManagerOption,
    graph_id: Annotated[
        str,
        typer.Option("--graph-id", help="JGF graph id"),
    ] = "pyverge",
    label: Annotated[
        str,
        typer.Option("--label", help="JGF graph label"),
    ] = "pyverge migration graph",
    manifest_version: Annotated[
        ManifestVersion,
        typer.Option("--manifest-version", help="Manifest contract version"),
    ] = ManifestVersion.V1,
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
        exporter = ManifestExporter(
            ManifestSpec(
                graph_id=graph_id,
                label=label,
                manifest_version=manifest_version,
                tool_version=__version__,
            ),
            JgfExporter(default_content_hasher()),
        )
        envelope = exporter.export(cast("GraphCatalog", mgr.registry), manager=manager)
        if output is not None:
            write_json_file(output, envelope)
        else:
            dump_json(envelope)

        if baseline is not None:
            base_envelope = json.loads(baseline.read_text())
            diff = ManifestDiff.compare(envelope, base_envelope)
            if diff.changed:
                typer.secho("Manifest divergence detected", fg=typer.colors.RED)
                for issue in diff.summary():
                    typer.echo(f"  - {issue}")
                raise typer.Exit(1)
            typer.secho("Manifest snapshot matches", fg=typer.colors.GREEN)
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1) from exc
