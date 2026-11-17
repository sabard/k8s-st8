"""Pure previews of declared transitions and their recovery boundaries."""

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .language import LanguageError, Plan, _json_value, ordered_steps


def state_hash(state: dict[str, Any]) -> str:
    """Hash a JSON-compatible managed-state projection, not a live cluster."""
    if not isinstance(state, dict):
        raise LanguageError("state must be a mapping")
    _json_value(state, "state")
    encoded = json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                         allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class StepPreview:
    id: str
    command: str
    target: str
    recovery: str
    impact: tuple[str, ...]
    snapshot: str | None
    before_hash: str
    after_hash: str
    projection_changed: bool


@dataclass(frozen=True)
class RecoveryStep:
    step_id: str
    recovery: str
    command: str
    target: str
    value: Any = None
    snapshot: str | None = None


@dataclass(frozen=True)
class Preview:
    initial_state: dict[str, Any]
    final_state: dict[str, Any]
    steps: tuple[StepPreview, ...]
    recovery: tuple[RecoveryStep, ...]
    recovery_complete: bool


def preview(plan: Plan, initial_state: dict[str, Any]) -> Preview:
    """Project a plan and describe recovery in reverse order.

    All steps are assumed completed successfully. Nothing is executed or verified.
    """
    state_hash(initial_state)
    state = copy.deepcopy(initial_state)
    initial = copy.deepcopy(initial_state)
    forward: list[StepPreview] = []
    reverse: list[RecoveryStep] = []
    for step in ordered_steps(plan):
        if step.target is None:
            raise LanguageError(f"step {step.id!r} has no target")
        before_hash = state_hash(state)
        existed = step.target in state
        old_value = copy.deepcopy(state.get(step.target))
        if step.command == "set":
            state[step.target] = copy.deepcopy(step.value)
        elif step.command == "delete":
            state.pop(step.target, None)
        elif step.command != "action":
            raise LanguageError(f"unknown command {step.command!r}")
        after_hash = state_hash(state)
        forward.append(StepPreview(step.id, step.command, step.target, step.recovery,
                                   step.impact, step.snapshot, before_hash, after_hash,
                                   before_hash != after_hash))
        if step.recovery == "irreversible":
            reverse.append(RecoveryStep(step.id, step.recovery, "manual", step.target,
                                        snapshot=step.snapshot))
        elif step.undo is not None:
            reverse.append(RecoveryStep(step.id, step.recovery, "action", step.undo))
        elif step.command in {"set", "delete"}:
            reverse.append(RecoveryStep(step.id, step.recovery,
                                        "set" if existed else "delete", step.target, old_value))
        else:
            raise LanguageError(f"step {step.id!r} has no recovery action")
    recovery: list[RecoveryStep] = []
    for entry in reversed(reverse):
        recovery.append(entry)
        if entry.command == "manual":
            break
    return Preview(initial, state, tuple(forward), tuple(recovery),
                   not recovery or recovery[-1].command != "manual")
