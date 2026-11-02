# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""Fixtures for the Celery adapter suites."""

from __future__ import annotations

import pytest
from celery import Celery

from pyverge.adapters.celery import CeleryRuntime


@pytest.fixture
def app() -> Celery:
    """An in-memory Celery app that executes tasks eagerly."""
    app = Celery("pyverge-tests", broker="memory://", backend="cache+memory://")
    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = True
    return app


@pytest.fixture
def runtime(manager) -> CeleryRuntime:
    """A bound runtime over the test manager instance."""
    instance = manager()
    return CeleryRuntime(instance, instance.runner())
