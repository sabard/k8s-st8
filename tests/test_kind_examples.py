import copy
import importlib.util
from pathlib import Path

from k8s_st8 import load_plan, preview, state_hash


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "kind"
spec = importlib.util.spec_from_file_location("kind_example", EXAMPLE / "preview.py")
assert spec is not None and spec.loader is not None
example = importlib.util.module_from_spec(spec)
spec.loader.exec_module(example)


def test_install_can_be_compensated_in_release_projection():
    result = preview(load_plan(EXAMPLE / "install.yaml"), {})
    assert result.final_state == {example.RELEASE: example.BASELINE[example.RELEASE]}
    assert result.recovery_complete
    assert (result.recovery[0].command, result.recovery[0].target) == ("delete", example.RELEASE)


def test_changes_reverse_to_baseline_hash():
    result = preview(load_plan(EXAMPLE / "changes.yaml"), example.BASELINE)
    assert result.final_state[example.MESSAGE] == "goodbye from st8"
    assert result.final_state[example.REPLICAS] == 2
    assert [step.step_id for step in result.recovery] == ["scale-up", "update-message"]
    restored = copy.deepcopy(result.final_state)
    for step in result.recovery:
        assert step.command == "set"
        restored[step.target] = step.value
    assert state_hash(restored) == state_hash(example.BASELINE)
    assert result.recovery_complete


def test_destructive_step_stops_at_snapshot_boundary():
    result = preview(load_plan(EXAMPLE / "destructive.yaml"), example.BASELINE)
    assert example.MESSAGE not in result.final_state
    assert state_hash(result.final_state) != state_hash(example.BASELINE)
    assert not result.recovery_complete
    assert result.recovery[0].command == "manual"
    assert result.recovery[0].snapshot
    assert result.initial_state[example.MESSAGE] == "hello from st8"
