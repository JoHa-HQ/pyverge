# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""Payload copy policy behaviour."""

from __future__ import annotations

import pytest
import semver

from pyverge.core.graph import latest_target_resolver
from pyverge.core.registry import Registry
from pyverge.runtime.types import CopyPolicy
from pyverge.schemas import PydanticModelAdapter
from tests.examples.pydantic.semver import UserV1, UserV2, migrate_v1_to_v2

_MODELS = [
    [
        PydanticModelAdapter,
        [
            semver.Version,
            "test",
            [UserV1, UserV2],
            [((UserV1, UserV2), migrate_v1_to_v2)],
        ],
    ]
]


def _payload() -> dict:
    return {
        "document": {
            "kind": "User",
            "version": "1.0.0",
            "name": "Alice",
            "email": "a@b.c",
            "role": "user",
        }
    }


@pytest.mark.parametrize("copy", ["deep", "shallow", "none"])
@pytest.mark.parametrize(
    "model_adapter, registry", _MODELS, indirect=["model_adapter", "registry"]
)
def test_copy_policy_controls_input_mutation(
    registry: Registry,
    runner_factory,
    copy: CopyPolicy,
) -> None:
    payload = _payload()

    result = runner_factory(copy=copy).run(
        payload,
        latest_target_resolver(registry),
        source_model=None,
        max_depth=-1,
        context=None,
    )

    assert result["document"]["version"] == "2.0.0"
    if copy == "deep":
        assert "age" not in payload["document"]
    else:
        assert payload["document"]["age"] is None
