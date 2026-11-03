from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from pyverge.core.types import HookState


def new_hook_state() -> HookState:
    return ContextVar("pyverge_hook_state", default={})


def push_state(state: HookState, key: int, value: Any) -> None:
    states = dict(state.get())
    states[key] = (*states.get(key, ()), value)
    state.set(states)


def pop_state(state: HookState, key: int) -> Any | None:
    states = dict(state.get())
    stack = states.get(key, ())
    if not stack:
        return None
    states[key] = stack[:-1]
    state.set(states)
    return stack[-1]


__all__ = ["new_hook_state", "pop_state", "push_state"]
