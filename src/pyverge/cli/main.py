import json
import sys
from itertools import pairwise
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import ValidationError
from rich import box
from rich.console import Console
from rich.table import Table

from pyverge.core import MissingReferenceError, SentinelEdge
from pyverge.core.types import (
    ManagerMigrationKey,
)

from ._helpers import (
    create_example_models_file,
    create_multi_manager_config,
    create_single_manager_config,
    load_json_file,
    print_next_steps,
    write_json_file,
)
from .config import (
    ConfigError,
    list_managers_from_module,
    resolve_manager,
)

app = typer.Typer(help="Schema evolution and migrations for versioned models")
console = Console()

ManagerOption = Annotated[
    str,
    typer.Option(
        ...,
        "--manager",
        "-m",
        help="Manager import path (module:object_path)",
    ),
]
SchemaOption = Annotated[
    str,
    typer.Option(..., "--schema", "-s", help="Schema name"),
]
VersionOption = Annotated[
    str,
    typer.Option(..., "--version", "-v", help="Schema version"),
]


@app.command()
def check(
    data: Annotated[
        Path, typer.Option(..., "--data", "-d", help="Path to data file (JSON)")
    ],
    schema: Annotated[str, typer.Option(..., "--schema", "-s", help="Schema name")],
    version: Annotated[
        str, typer.Option(..., "--version", "-v", help="Schema version")
    ],
    manager: ManagerOption,
) -> None:
    """Check a payload against a schema version."""
    try:
        mgr = resolve_manager(manager)
        data_dict = load_json_file(data)

        mgr.validate(data_dict, schema, version)

        typer.secho(f"✓ Valid against {schema} v{version}", fg=typer.colors.GREEN)
        raise typer.Exit(0)

    except ValidationError as e:
        typer.secho("✗ Validation failed", fg=typer.colors.RED)
        typer.secho("\nValidation errors:", fg=typer.colors.RED)
        for error in e.errors():
            field = ".".join(str(loc) for loc in error["loc"])
            typer.echo(f"  • {field}: {error['msg']}")
        raise typer.Exit(1) from e
    except ConfigError as e:
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(1) from e
    except FileNotFoundError as e:
        typer.secho(f"File not found: {e}", fg=typer.colors.RED)
        raise typer.Exit(1) from e
    except json.JSONDecodeError as e:
        typer.secho(f"Invalid JSON in {data}: {e}", fg=typer.colors.RED)
        raise typer.Exit(1) from e
    except typer.Exit:
        raise
    except Exception as e:
        typer.secho(f"Validation error: {e}", fg=typer.colors.RED)
        raise typer.Exit(1) from e


@app.command()
def managers(
    module: Annotated[
        str, typer.Argument(..., help="Module path to inspect for managers")
    ],
) -> None:
    """List Managers defined in a module."""
    try:
        names = list_managers_from_module(module)

        table = Table(title=f"Managers in {module}", box=box.SQUARE)
        table.add_column("Name", style="cyan")

        for name in sorted(names):
            table.add_row(name)

        console.print(table)

    except ImportError as e:
        typer.secho(f"Cannot import module '{module}': {e}", fg=typer.colors.RED)
        raise typer.Exit(1) from e


@app.command()
def info(
    manager: Annotated[
        str, typer.Argument(..., help="Manager import path (module:object_path)")
    ],
) -> None:
    """Show information about a specific manager."""
    try:
        mgr = resolve_manager(manager)

        typer.secho(f"Manager: {manager}", bold=True)
        typer.echo("")

        versions = mgr.list_versions()
        models = sorted({v.model.__name__ for v in versions})

        if not models:
            typer.secho("No models registered", fg=typer.colors.YELLOW)
            return

        typer.secho("Registered Models:", bold=True)
        typer.echo("")

        for model_name in models:
            typer.secho(f"  {model_name}", bold=True)
            for v in versions:
                if v.model.__name__ == model_name:
                    typer.echo(f"    • v{v.version[1]}")

        typer.echo(f"\nTotal: {len(models)} models")

    except ConfigError as e:
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(1) from e
    except typer.Exit:
        raise
    except Exception as e:
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(1) from e


@app.command()
def diff(
    schema: Annotated[str, typer.Option(..., "--schema", "-s", help="Schema name")],
    from_version: Annotated[
        str, typer.Option(..., "--from", "-f", help="Source version")
    ],
    to_version: Annotated[str, typer.Option(..., "--to", "-t", help="Target version")],
    manager: ManagerOption,
    format: Annotated[
        str, typer.Option(..., "--format", help="Output format (json)")
    ] = "json",
) -> None:
    """Show differences between schema versions."""
    try:
        mgr = resolve_manager(manager)
        diff_result = mgr.diff(ManagerMigrationKey(schema, from_version, to_version))

        if format == "json":
            typer.echo(json.dumps(diff_result.render(), indent=2, default=str))
        else:
            typer.secho(f"Unknown format: {format}", fg=typer.colors.RED)
            raise typer.Exit(1)

    except ConfigError as e:
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(1) from e
    except typer.Exit:
        raise
    except Exception as e:
        typer.secho(f"Diff error: {e}", fg=typer.colors.RED)
        raise typer.Exit(1) from e


def _dump_json(value: Any) -> None:
    typer.echo(json.dumps(value, indent=2, default=str))


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


@app.command()
def doctor(
    manager: ManagerOption,
    format: Annotated[
        str, typer.Option("--format", help="Output format (text/json)")
    ] = "text",
) -> None:
    """Validate registry health for CI."""
    try:
        mgr = resolve_manager(manager)
        issues: list[str] = []

        try:
            mgr.engine.validate()
        except MissingReferenceError as exc:
            issues.append(str(exc))

        registry = mgr.registry
        for kind in registry.entities:
            versions = registry.kind_versions(kind)
            for source, target in pairwise(versions):
                if not registry.has_migration(SentinelEdge.from_pair(source, target)):
                    issues.append(
                        f"{kind}: missing migration "
                        f"{source.version[1]} -> {target.version[1]}"
                    )

        report = {
            "status": "ok" if not issues else "error",
            "manager": manager,
            "kinds": len(registry.entities),
            "versions": len(registry.versions),
            "issues": issues,
        }
        if format == "json":
            _dump_json(report)
        else:
            typer.secho(
                "Registry healthy" if not issues else "Registry issues found",
                fg=typer.colors.GREEN if not issues else typer.colors.RED,
            )
            for issue in issues:
                typer.echo(f"  - {issue}")
        raise typer.Exit(0 if not issues else 1)
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1) from exc


@app.command()
def migrate(
    data: Annotated[Path, typer.Argument(help="Payload JSON file")],
    manager: ManagerOption,
    target: Annotated[
        str, typer.Option("--target", "-t", help="Target policy/version")
    ] = "latest",
    context: Annotated[
        str | None, typer.Option("--context", help="Context JSON object")
    ] = None,
    context_file: Annotated[
        Path | None, typer.Option("--context-file", help="Context JSON file")
    ] = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write migrated payload")
    ] = None,
    in_place: Annotated[
        bool, typer.Option("--in-place", help="Overwrite the input payload")
    ] = False,
    check: Annotated[
        bool, typer.Option("--check", help="Fail if migration does not converge")
    ] = False,
) -> None:
    """Migrate a payload and optionally write the result."""
    if output is not None and in_place:
        typer.secho(
            "--output and --in-place are mutually exclusive", fg=typer.colors.RED
        )
        raise typer.Exit(2)
    try:
        mgr = resolve_manager(manager)
        payload = load_json_file(data)
        runtime_context = None
        if context_file is not None:
            runtime_context = load_json_file(context_file)
        elif context is not None:
            runtime_context = json.loads(context)

        result = mgr.migrate(payload, target=target, context=runtime_context)

        if check:
            raise typer.Exit(0)
        if in_place:
            write_json_file(data, result)
        elif output is not None:
            write_json_file(output, result)
        else:
            _dump_json(result)
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1) from exc
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1) from exc
    except typer.Exit:
        raise
    except Exception as exc:
        typer.secho(f"Migration failed: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc


@app.command()
def validate(
    manager: ManagerOption,
    schema: SchemaOption,
    version: VersionOption,
    files: Annotated[
        list[Path] | None, typer.Argument(help="Payload files or directories")
    ] = None,
    stdin: Annotated[
        bool, typer.Option("--stdin", help="Read a payload from stdin")
    ] = False,
    format: Annotated[
        str, typer.Option("--format", help="Output format (text/json)")
    ] = "text",
    fail_fast: Annotated[
        bool, typer.Option("--fail-fast", help="Stop on first failure")
    ] = False,
) -> None:
    """Validate one or more payloads against a schema version."""
    try:
        mgr = resolve_manager(manager)
        paths: list[Path] = []
        for file in files or []:
            if file.is_dir():
                paths.extend(sorted(file.rglob("*.json")))
            else:
                paths.append(file)
        if not paths and not stdin:
            typer.secho("No input files (or use --stdin)", fg=typer.colors.RED)
            raise typer.Exit(2)

        results: list[dict[str, Any]] = []
        failed = 0
        for path in paths:
            try:
                mgr.validate(load_json_file(path), schema, version)
                results.append({"path": str(path), "valid": True})
            except Exception as exc:
                failed += 1
                results.append({"path": str(path), "valid": False, "error": str(exc)})
                if fail_fast:
                    break
        if stdin:
            try:
                mgr.validate(json.load(sys.stdin), schema, version)
                results.append({"path": "<stdin>", "valid": True})
            except Exception as exc:
                failed += 1
                results.append({"path": "<stdin>", "valid": False, "error": str(exc)})

        if format == "json":
            _dump_json({"schema": schema, "version": version, "results": results})
        else:
            for result in results:
                mark = "OK" if result["valid"] else "FAIL"
                typer.echo(f"{mark} {result['path']}")
                if not result["valid"]:
                    typer.echo(f"  {result['error']}")
        raise typer.Exit(0 if failed == 0 else 1)
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1) from exc


@app.command()
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
            _dump_json({"breaking": breaking, "migrations": reports})
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


@app.command()
def init(
    path: Annotated[Path, typer.Argument(help="Project directory")] = Path("."),
    use_pyproject: Annotated[
        bool, typer.Option("--pyproject", help="Write pyproject.toml config")
    ] = False,
    multiple: Annotated[
        bool, typer.Option("--multiple", help="Scaffold multi-manager config")
    ] = False,
) -> None:
    """Scaffold models and manager configuration."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        create_example_models_file(path / "models.py")
        if multiple:
            create_multi_manager_config(path, use_pyproject)
        else:
            create_single_manager_config(path, use_pyproject)
        print_next_steps(multiple)
    except OSError as exc:
        typer.secho(f"Initialization failed: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc


@app.command()
def export(
    manager: ManagerOption,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write manifest file")
    ] = None,
) -> None:
    """Export the registered graph as a machine-readable manifest."""
    try:
        mgr = resolve_manager(manager)
        registry = mgr.registry
        manifest = {
            "kinds": {
                kind: [
                    {
                        "version": str(version.version[1]),
                        "model": getattr(version.model, "__name__", None),
                        "fields": sorted(version.fields),
                        "references": [
                            [ref_kind, str(ref_version)]
                            for ref_kind, ref_version in sorted(version.references)
                        ],
                    }
                    for version in registry.kind_versions(kind)
                ]
                for kind in registry.entities
            },
            "migrations": [
                {
                    "kind": edge.kind,
                    "from": str(edge.source.version[1]),
                    "to": str(edge.target.version[1]),
                    "backward_compatible": edge.diff.is_backward_compatible,
                }
                for kind in registry.kinds
                for edge in registry.migrations(kind)
            ],
        }
        if output is not None:
            write_json_file(output, manifest)
        else:
            _dump_json(manifest)
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1) from exc


if __name__ == "__main__":
    app()
