"""Test forking scenarios: shared version classes across multiple managers.

Demonstrates:
- Two managers with divergent migration paths
- Version classes shared between managers, each manager owning separate wrapper classes
- Isolated migration results from each path
- Navigation through manager explicitly (not via class attributes)
"""

from typing import Annotated

from pydantic import BaseModel, Field

from pydantic_migrator.migration import ModelManager, ModelVersion
from pydantic_migrator.models import ManagerSettings


def test_fork_migration_path() -> None:
    """Two managers diverging from the same version classes."""

    class UserV1(BaseModel):
        name: str
        version: str = "1.0.0"

    class UserV2(BaseModel):
        name: str
        email: str
        version: str = "2.0.0"

    class UserV3Upstream(BaseModel):
        name: str
        email: str
        age: int
        version: str = "3.0.0"

    class UserV4Upstream(BaseModel):
        name: str
        email: str
        age: int
        status: str
        version: str = "4.0.0"

    class UserV3Fork(BaseModel):
        name: str
        email: str
        role: str
        version: str = "3.0.0"

    class UserV4Fork(BaseModel):
        name: str
        email: str
        role: str
        permissions: list[str]
        version: str = "4.0.0"

    UpstreamUser = Annotated[
        UserV1 | UserV2 | UserV3Upstream | UserV4Upstream,
        Field(discriminator="version"),
    ]

    ForkUser = Annotated[
        UserV1 | UserV2 | UserV3Fork | UserV4Fork,
        Field(discriminator="version"),
    ]

    class UpstreamContainer(BaseModel):
        user: UpstreamUser

    class ForkContainer(BaseModel):
        user: ForkUser

    # -------------------------------------------------------------------
    # Upstream manager: v1 -> v2 -> v3_up -> v4_up
    # -------------------------------------------------------------------

    UpstreamManager = ModelManager["UpstreamContainer"]

    @UpstreamManager.model("1.0.0")
    class _UpV1(UserV1):
        pass

    @UpstreamManager.model("2.0.0")
    class _UpV2(UserV2):
        pass

    @UpstreamManager.model("3.0.0")
    class _UpV3(UserV3Upstream):
        pass

    @UpstreamManager.model("4.0.0")
    class _UpV4(UserV4Upstream):
        pass

    @UpstreamManager.migration("1.0.0", "2.0.0")
    def up_v1_to_v2(data: dict) -> dict:
        data["email"] = "unknown@example.com"
        return data

    @UpstreamManager.migration("2.0.0", "3.0.0")
    def up_v2_to_v3(data: dict) -> dict:
        data["age"] = 0
        return data

    @UpstreamManager.migration("3.0.0", "4.0.0")
    def up_v3_to_v4(data: dict) -> dict:
        data["status"] = "active"
        return data

    upstream = UpstreamManager(ManagerSettings(version_property="version"))

    # -------------------------------------------------------------------
    # Fork manager: v1 -> v2 -> v3_fork -> v4_fork
    # -------------------------------------------------------------------

    ForkManager = ModelManager["ForkContainer"]

    @ForkManager.model("1.0.0")
    class _ForkV1(UserV1):
        pass

    @ForkManager.model("2.0.0")
    class _ForkV2(UserV2):
        pass

    @ForkManager.model("3.0.0")
    class _ForkV3(UserV3Fork):
        pass

    @ForkManager.model("4.0.0")
    class _ForkV4(UserV4Fork):
        pass

    @ForkManager.migration("1.0.0", "2.0.0")
    def fork_v1_to_v2(data: dict) -> dict:
        data["email"] = "fork@example.com"
        return data

    @ForkManager.migration("2.0.0", "3.0.0")
    def fork_v2_to_v3(data: dict) -> dict:
        data["role"] = "user"
        return data

    @ForkManager.migration("3.0.0", "4.0.0")
    def fork_v3_to_v4(data: dict) -> dict:
        data["permissions"] = ["read"]
        return data

    fork = ForkManager(ManagerSettings(version_property="version"))

    # -------------------------------------------------------------------
    # Assertions
    # -------------------------------------------------------------------

    source = {"name": "Alice", "version": "1.0.0"}

    # Each manager has its own registry
    assert UpstreamManager._registry is not ForkManager._registry

    # Same source data produces different results for each path
    up_v4 = upstream.migrate(dict(source), "User", "1.0.0", "4.0.0")
    fork_v4 = fork.migrate(dict(source), "User", "1.0.0", "4.0.0")

    assert up_v4.email == "unknown@example.com"
    assert up_v4.age == 0
    assert up_v4.status == "active"

    assert fork_v4.email == "fork@example.com"
    assert fork_v4.role == "user"
    assert fork_v4.permissions == ["read"]

    # Version classes don't carry manager references
    assert not hasattr(_UpV1, "manager")
    assert not hasattr(_ForkV1, "manager")
    assert not hasattr(_UpV1, "versioned_model")

    # Navigation goes through the manager explicitly
    up_v1 = UpstreamManager._version_map[("User", ModelVersion.parse("1.0.0"))]
    fork_v1 = ForkManager._version_map[("User", ModelVersion.parse("1.0.0"))]
    assert up_v1.manager is not fork_v1.manager
