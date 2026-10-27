from __future__ import annotations

import html
from pathlib import Path
from typing import Any


def rows(document: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in document.get("benchmarks", []):
        stats = item.get("stats", {})
        mean = float(stats.get("mean", 0.0))
        result.append(
            {
                "name": item.get("fullname") or item.get("name", ""),
                "mean": mean,
                "median": float(stats.get("median", 0.0)),
                "min": float(stats.get("min", 0.0)),
                "max": float(stats.get("max", 0.0)),
                "ops": 1.0 / mean if mean else 0.0,
            }
        )
    return sorted(result, key=lambda row: row["name"])


def render_markdown(values: list[dict[str, Any]]) -> str:
    lines = [
        "| Benchmark | Mean | Median | Min | Max | OPS |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in values:
        lines.append(
            f"| {row['name']} | {row['mean']:.6f} | {row['median']:.6f} | "
            f"{row['min']:.6f} | {row['max']:.6f} | {row['ops']:,.2f} |"
        )
    return "\n".join(lines) + "\n"


def render_html(values: list[dict[str, Any]]) -> str:
    cells = "\n".join(
        "<tr>"
        f"<td>{html.escape(row['name'])}</td>"
        f"<td>{row['mean']:.6f}</td>"
        f"<td>{row['median']:.6f}</td>"
        f"<td>{row['min']:.6f}</td>"
        f"<td>{row['max']:.6f}</td>"
        f"<td>{row['ops']:,.2f}</td>"
        "</tr>"
        for row in values
    )
    return (
        "<table><thead><tr><th>Benchmark</th><th>Mean</th><th>Median</th>"
        "<th>Min</th><th>Max</th><th>OPS</th></tr></thead>"
        f"<tbody>{cells}</tbody></table>\n"
    )


def write_reports(json_path: Path, document: dict[str, Any]) -> None:
    values = rows(document)
    json_path.with_suffix(".md").write_text(render_markdown(values))
    json_path.with_suffix(".html").write_text(render_html(values))


__all__ = ["render_html", "render_markdown", "rows", "write_reports"]
