# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""Adapter benchmark harness.

Benchmarks measure pyverge host adapters (FastStream, FastMCP), not engine
internals. Payloads are synthesized from the registered models with Hypothesis
and validated against their source version (see :mod:`tests.benchmarks.factories`).
"""
