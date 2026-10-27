"""Adapter benchmark harness.

Benchmarks measure pyverge host adapters (FastStream, FastMCP), not engine
internals. Payloads are synthesized from the registered models with Hypothesis
and validated against their source version (see :mod:`tests.benchmarks.factories`).
"""
