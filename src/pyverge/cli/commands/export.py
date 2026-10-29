from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from .._helpers import write_json_file
from ..config import ConfigError, resolve_manager
from ._shared import ManagerOption, dump_json


def export(
    manager: ManagerOption,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write manifest file")
    ] = None,
) -> None:
    try:
        mgr = resolve_manager(manager)
        registry = mgr.registry
        manifest = {
            "kinds": {
                kind: [
                    {
                        "version": str(version.version),
                        "model": version.model_id,
                        "fields": sorted(version.fields),
                        "references": [
                            [
                                reference.kind,
                                str(reference.version),
                            ]
                            for reference in sorted(
                                version.references,
                                key=lambda item: (
                                    item.namespace,
                                    item.kind,
                                    str(item.version),
                                ),
                            )
                        ],
                    }
                    for version in registry.kind_versions(kind)
                ]
                for kind in registry.entities
            },
            "migrations": [
                {
                    "kind": edge.kind,
                    "from": str(edge.source.version),
                    "to": str(edge.target.version),
                }
                for kind in registry.kinds
                for edge in registry.migrations(kind)
            ],
        }
        if output is not None:
            write_json_file(output, manifest)
        else:
            dump_json(manifest)
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1) from exc
