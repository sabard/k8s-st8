from pathlib import Path

import pytest

from k8s_st8 import LanguageError, load_plan, parse_plan, preview, state_hash


def test_example_orders_steps_and_stops_recovery():
    plan = load_plan(Path(__file__).resolve().parents[1] / "examples" / "upgrade.yaml")
    initial = {"traffic/production/payments": {"version": "v3", "weight_percent": 100}}
    result = preview(plan, initial)
    assert [s.id for s in result.steps] == ["chart", "migration", "traffic"]
    assert [s.step_id for s in result.recovery] == ["traffic", "migration"]
    assert result.recovery[0].value == initial["traffic/production/payments"]
    assert result.recovery[1].command == "manual"
    assert result.recovery[1].snapshot
    assert not result.recovery_complete
    assert initial == result.initial_state


def test_hash_and_recovery_with_noops_and_null():
    plan = parse_plan("""
version: 1
name: test
steps:
  - {id: a, command: set, target: a, value: null, recovery: reversible, impact: [configuration]}
  - {id: b, command: delete, target: missing, recovery: reversible, impact: [configuration]}
  - {id: c, command: set, target: b, value: 1, recovery: reversible, impact: [configuration]}
""")
    initial = {"b": 1, "a": None}
    result = preview(plan, initial)
    assert state_hash(initial) == state_hash({"a": None, "b": 1})
    assert state_hash(initial) == state_hash(result.final_state)
    assert all(not s.projection_changed for s in result.steps)
    assert result.recovery[-1].command == "set"
    assert result.recovery[-1].value is None
    assert result.recovery[1].command == "delete"
    assert result.recovery_complete
    assert state_hash({"a": True}) != state_hash({"a": 1})


def test_reverse_restores_projection():
    plan = parse_plan("""
version: 1
name: test
steps:
  - {id: one, command: set, target: a, value: [new], recovery: reversible, impact: [configuration]}
  - {id: two, command: delete, target: b, recovery: reversible, impact: [configuration]}
  - {id: three, command: set, target: c, value: 3, recovery: reversible, impact: [configuration]}
""")
    initial = {"a": [1], "b": None}
    result = preview(plan, initial)
    restored = result.final_state.copy()
    for step in result.recovery:
        if step.command == "set":
            restored[step.target] = step.value
        else:
            restored.pop(step.target, None)
    assert state_hash(restored) == state_hash(initial)
    assert initial == {"a": [1], "b": None}


def test_forward_dependencies_and_explicit_compensation():
    plan = parse_plan("""
version: 1
name: test
steps:
  - id: second
    command: action
    target: upgrade cluster
    depends_on: [first]
    recovery: compensatable
    undo: restore control plane
    impact: [infrastructure]
  - {id: first, command: set, target: x, value: true, recovery: reversible, impact: [configuration]}
""")
    result = preview(plan, {})
    assert [s.id for s in result.steps] == ["first", "second"]
    assert result.recovery[0].target == "restore control plane"
    assert result.steps[1].before_hash == result.steps[1].after_hash


@pytest.mark.parametrize("steps", [
    "- {id: a, command: nope, recovery: reversible, impact: [traffic]}",
    "- {id: a, command: set, target: x, recovery: reversible, impact: [traffic]}",
    "- {id: a, command: action, target: x, recovery: reversible, impact: [traffic]}",
    "- {id: a, command: delete, target: x, recovery: irreversible, impact: [traffic]}",
    "- {id: a, command: action, target: x, recovery: irreversible, snapshot: backup, undo: x, impact: [traffic]}",
    "- {id: a, command: delete, target: x, recovery: reversible, impact: [typo]}",
    "- {id: a, command: delete, target: x, recovery: reversible, impact: [traffic], depends_on: [missing]}",
    "- {id: a, command: delete, target: x, recovery: reversible, impact: [traffic], depends_on: [a]}",
    "- {id: a, command: delete, target: x, recovery: reversible, impact: [traffic], extra: 1}",
    "- {id: a, id: b, command: delete, target: x, recovery: reversible, impact: [traffic]}",
    "- {id: a, command: set, target: x, value: .nan, recovery: reversible, impact: [traffic]}",
    "- {id: a, command: set, target: x, value: 2026-11-17, recovery: reversible, impact: [traffic]}",
])
def test_invalid_plans(steps):
    with pytest.raises(LanguageError):
        parse_plan(f"version: 1\nname: test\nsteps:\n  {steps}\n")


@pytest.mark.parametrize("value", [float("nan"), {1: "not a string"}, {1, 2}])
def test_invalid_state(value):
    with pytest.raises(LanguageError):
        state_hash({"x": value})


def test_input_and_preview_are_independent():
    plan = parse_plan("""
version: 1
name: test
steps:
  - {id: a, command: set, target: x, value: [1], recovery: reversible, impact: [configuration]}
""")
    initial = {"x": [0]}
    result = preview(plan, initial)
    result.final_state["x"].append(2)
    assert plan.steps[0].value == [1]
    assert initial == {"x": [0]}
    assert result.recovery[0].value == [0]
