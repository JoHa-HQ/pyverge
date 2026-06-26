"""Registry pattern: coordinate multiple Manager classes.

Demonstrates using a Registry to manage multiple model families together,
with shared defaults and batch operations. The Registry handles all static
wiring (model registration, migrations) from a single declarative config.

Benefits:
- Declarative schema definition in one place
- Shared configuration defaults with per-manager overrides
- Cross-cutting operations (validation, migration testing, schema dump)
- Single entry point for model family coordination
"""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field

from pydantic_migrator import ModelManager, Registry


class Status(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class UserV1(BaseModel):
    username: str
    email: str


class UserV2(BaseModel):
    username: str
    email: str
    full_name: str | None = None
    status: Status = Status.ACTIVE


User = Annotated[UserV1 | UserV2, Field(discriminator="version")]


class UserContainer(BaseModel):
    document: User


class ProjectV1(BaseModel):
    name: str
    owner: str


class ProjectV2(BaseModel):
    name: str
    owner: str
    description: str | None = None
    visibility: str = "private"


Project = Annotated[ProjectV1 | ProjectV2, Field(discriminator="version")]


class ProjectContainer(BaseModel):
    document: Project


class IssueV1(BaseModel):
    title: str
    issue_type: str
    priority: str


class IssueV2(BaseModel):
    title: str
    issue_type: str
    priority: str
    assignee: str | None = None
    project: str | None = None


Issue = Annotated[IssueV1 | IssueV2, Field(discriminator="version")]


class IssueContainer(BaseModel):
    document: Issue


def migrate_user(data: dict) -> dict:
    data["full_name"] = None
    data["status"] = "active"
    return data


def migrate_project(data: dict) -> dict:
    data["description"] = None
    data["visibility"] = "private"
    return data


def migrate_issue(data: dict) -> dict:
    data["assignee"] = None
    data["project"] = None
    return data


# The Registry creates internal Manager classes, registers models and
# migrations, and merges per-manager config with defaults.

registry = Registry(
    defaults={"version_property": "version"},
    managers={
        UserContainer: {
            "versions": {
                "1.0.0": UserV1,
                "2.0.0": UserV2,
            },
            "migrations": {
                ("1.0.0", "2.0.0"): migrate_user,
            },
        },
        ProjectContainer: {
            "config": {"version_property": "schema_version"},
            "versions": {
                "1.0.0": ProjectV1,
                "2.0.0": ProjectV2,
            },
            "migrations": {
                ("1.0.0", "2.0.0"): migrate_project,
            },
        },
        IssueContainer: {
            "versions": {
                "1.0.0": IssueV1,
                "2.0.0": IssueV2,
            },
            "migrations": {
                ("1.0.0", "2.0.0"): migrate_issue,
            },
        },
    },
)
