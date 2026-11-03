from .base import HealthLinter
from .compatibility import CompatibilityLinter, CompatibilityReport
from .edges import MissingEdgeEndpointsLinter
from .migrations import MissingMigrationsLinter
from .references import MissingReferencesLinter

DEFAULT_HEALTH_LINTERS: tuple[HealthLinter, ...] = (
    MissingReferencesLinter(),
    MissingEdgeEndpointsLinter(),
    MissingMigrationsLinter(),
)

__all__ = [
    "DEFAULT_HEALTH_LINTERS",
    "CompatibilityLinter",
    "CompatibilityReport",
    "HealthLinter",
    "MissingEdgeEndpointsLinter",
    "MissingMigrationsLinter",
    "MissingReferencesLinter",
]
