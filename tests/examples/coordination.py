"""Coordinator pattern: coordinate multiple Manager classes.

Demonstrates using a Coordinator to manage multiple model families together,
with shared defaults and batch operations. The Coordinator handles all static
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
