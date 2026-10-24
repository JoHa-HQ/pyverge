"""Check structural compatibility of migrations."""

from __future__ import annotations

from typing import Annotated

import typer

from pyverge.core.types import ManagerMigrationKey
from pyverge.versioning import CompatibilityReport

from ..config import ConfigError, resolve_manager
from ._shared import ManagerOption, dump_json


def compat(
    manager: ManagerOption,
    schema: Annotated[
        str | None, typer.Option("--schema", "-s", help="Schema name")
    ] = None,
    from_version: Annotated[
        str | None, typer.Option("--from", "-f", help="Source version")
    ] = None,
    to_version: Annotated[
        str | None, typer.Option("--to", "-t", help="Target version")
    ] = None,
    fail_on_breaking: Annotated[
        bool, typer.Option("--fail-on-breaking", help="Exit 3 on breaking change")
    ] = False,
    format: Annotated[
        str, typer.Option("--format", help="Output format (text/json)")
    ] = "text",
) -> None:
    """Check structural compatibility of migrations."""
    try:
        mgr = resolve_manager(manager)
        keys: list[ManagerMigrationKey] = []
        if schema is not None:
            if from_version is None or to_version is None:
                typer.secho("--schema requires --from and --to", fg=typer.colors.RED)
                raise typer.Exit(2)
            keys.append(ManagerMigrationKey(schema, from_version, to_version))
        else:
            for kind in mgr.registry.kinds:
                for edge in mgr.registry.migrations(kind):
                    keys.append(
                        ManagerMigrationKey(
                            kind,
                            str(edge.source.version[1]),
                            str(edge.target.version[1]),
                        )
                    )

        identity = frozenset({mgr.adapter.kind_property, mgr.adapter.version_property})
        reports = [
            CompatibilityReport.from_diff(
                mgr.get_migration(key).diff,
                identity_fields=identity,
            )
            for key in keys
        ]
        breaking = any(report.structural_breaking for report in reports)
        if format == "json":
            dump_json(
                {
                    "breaking": breaking,
                    "migrations": [
                        {
                            "kind": report.kind,
                            "from": report.source_version,
                            "to": report.target_version,
                            "structural_breaking": report.structural_breaking,
                            "added": list(report.added_fields),
                            "removed": list(report.removed_fields),
                            "modified": list(report.modified_fields),
                        }
                        for report in reports
                    ],
                }
            )
        else:
            for report in reports:
                status = "BREAKING" if report.structural_breaking else "ok"
                typer.echo(
                    f"{status} {report.kind} "
                    f"{report.source_version} -> {report.target_version}"
                )
        exit_code = 3 if breaking and fail_on_breaking else 0
        raise typer.Exit(exit_code)
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1) from exc
