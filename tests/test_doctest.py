"""Run doctests from the library's public docstrings.

Kept separate from the unit-test suite so ``--doctest-modules`` does not
re-collect the ``tests/examples`` package (duplicate module basenames).
"""

import doctest
import importlib

import pytest

DOCTEST_MODULES = [
    "pyverge.migration.registry",
]


@pytest.mark.parametrize("module_name", DOCTEST_MODULES)
def test_doctest(module_name: str) -> None:
    module = importlib.import_module(module_name)
    results = doctest.testmod(module, verbose=False)
    assert results.failed == 0, f"{module_name} doctests failed: {results.failed}"
