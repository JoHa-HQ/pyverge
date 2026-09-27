"""Every migration callable must be AST-discoverable.

The engine reconstructs older models by parsing each migration's source AST, so
a callable whose intent it cannot read silently reconstructs the wrong schema.
This pins the contract: every edge in the graph must yield the field it adds or
removes when discovered.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
import semver
from fastmcp_demo.domain import migrations

from pyverge.core.versioning import VersionNode
from pyverge.reflection.discovery import CallableDiffDiscovery

#: Discovery ignores the endpoints for callables; pass meta nodes so the
#: signature is satisfied without registering models.
_META = cast(
    "Any",
    VersionNode(_model=None, _value=semver.Version(1, 0, 0), _kind="search_weather"),
)

#: edge callable -> (field it adds, field it removes).
EDGE_EFFECTS = {
    migrations.add_humidity: ("humidity", None),
    migrations.add_wind: ("wind", None),
    migrations.drop_humidity: (None, "humidity"),
    migrations.drop_wind: (None, "wind"),
}


@pytest.mark.parametrize(
    ("func", "effect"),
    list(EDGE_EFFECTS.items()),
    ids=[fn.__name__ for fn in EDGE_EFFECTS],
)
def test_callable_is_ast_discoverable(
    func, effect: tuple[str | None, str | None]
) -> None:
    added, removed = effect
    diff = CallableDiffDiscovery().discover(func, source=_META, target=_META)
    if added is not None:
        assert added in diff.added_fields
    if removed is not None:
        assert removed in diff.removed_fields
