"""Execution package (runtime, entry extraction, backends)."""

from .backends import PlainBackend, ProcessBackend
from .coordinator import ExecutionCoordinator
from .direction import (
    AnyDirection,
    BackwardDirection,
    DirectionPolicy,
    ForwardDirection,
    direction_policy,
)
from .errors import (
    AsyncExecutionRequired,
    ExecutionError,
    ExecutionModeError,
    SyncExecutionRequired,
)
from .extractors import CompositeExtractor, ContainerExtractor, SchemaFieldsExtractor
from .hooks import MigrationHook
from .path import Path
from .path_resolver import PathResolver
from .plan import (
    BackendDeclaration,
    ExecutionPlan,
    ExtractedEntry,
    PathPlan,
    PathPlanEntry,
    PlanningOptions,
    PolicyDecision,
)
from .planner import ExecutionPlanner
from .policy import PolicyEngine
from .runner import Runner
from .targets import (
    earliest_target_resolver,
    fixed_target_resolver,
    latest_target_resolver,
    multi_target_resolver,
    skip_target_resolver,
)
from .types import (
    ConcurrencyBackend,
    Entry,
    EntryExtractor,
    RuntimeCapabilities,
    RuntimePort,
)

__all__ = [
    "AnyDirection",
    "AsyncExecutionRequired",
    "BackendDeclaration",
    "BackwardDirection",
    "CompositeExtractor",
    "ConcurrencyBackend",
    "ContainerExtractor",
    "DirectionPolicy",
    "Entry",
    "EntryExtractor",
    "ExecutionCoordinator",
    "ExecutionError",
    "ExecutionModeError",
    "ExecutionPlan",
    "ExecutionPlanner",
    "ExtractedEntry",
    "ForwardDirection",
    "MigrationHook",
    "Path",
    "PathPlan",
    "PathPlanEntry",
    "PathResolver",
    "PlainBackend",
    "PlanningOptions",
    "PolicyDecision",
    "PolicyEngine",
    "ProcessBackend",
    "Runner",
    "RuntimeCapabilities",
    "RuntimePort",
    "SchemaFieldsExtractor",
    "SyncExecutionRequired",
    "direction_policy",
    "earliest_target_resolver",
    "fixed_target_resolver",
    "latest_target_resolver",
    "multi_target_resolver",
    "skip_target_resolver",
]
