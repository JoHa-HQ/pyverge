"""Model reflection: reconstruct missing model versions from an anchor.

The reflection package owns the diff model and migration-format discovery.
Reconstruction itself is a pure transformation: the provider adapter rebuilds
a model from an anchor and a diff via ``materialize``.  It depends on ``core``
(types, render, versioning) and ``registry`` but not on the migration engine.
"""

from .diff import Diff
from .discovery import (
    CallableDiffDiscovery,
    CompositeDiffDiscovery,
    DiffDiscovery,
    JsonPatchDiffDiscovery,
)

__all__ = [
    "CallableDiffDiscovery",
    "CompositeDiffDiscovery",
    "Diff",
    "DiffDiscovery",
    "JsonPatchDiffDiscovery",
]
