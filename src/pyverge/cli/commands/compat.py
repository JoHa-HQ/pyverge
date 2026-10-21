"""Check structural compatibility of migrations."""

from __future__ import annotations

from typing import Annotated, Any

import typer

from pyverge.core.types import ManagerMigrationKey

from ..config import ConfigError, resolve_manager
from ._shared import ManagerOption, dump_json


def _compat_report(manager: Any, key: ManagerMigrationKey) -> dict[str, Any]:
    edge = manager.get_migration(key)
    diff = edge.diff
    identity = {manager.adapter.version_property, manager.adapter.kind_property}
    added = [field for field in diff.added_fields if field not in identity]
    removed = [field for field in diff.removed_fields if field not in identity]
    modified = {
        field: change
        for field, change in diff.modified_fields.items()
        if field not in identity
    }
    structural = (
        bool(removed)
        or any("type_changed" in change for change in modified.values())
        or any("required_changed" in change for change in modified.values())
        or any(diff.is_added_required(field) for field in added)
    )
    return {
        "kind": key.kind,
        "from": key.source_version,
        "to": key.target_version,
        "structural_breaking": structural,
        "declared_backward_compatible": diff.is_backward_compatible,
        "breaking": structural and not diff.is_backward_compatible,
        "added": added,
        "removed": removed,
        "modified": sorted(modified),
    }


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

        reports = [_compat_report(mgr, key) for key in keys]
        breaking = any(report["breaking"] for report in reports)
        if format == "json":
            dump_json({"breaking": breaking, "migrations": reports})
        else:
            for report in reports:
                status = "BREAKING" if report["breaking"] else "ok"
                typer.echo(
                    f"{status} {report['kind']} {report['from']} -> {report['to']}"
                )
        exit_code = 3 if breaking and fail_on_breaking else 0
        raise typer.Exit(exit_code)
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1) from exc
