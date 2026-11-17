"""Preview the kind walkthrough's manually supplied state projections."""

from pathlib import Path

from k8s_st8 import load_plan, preview, state_hash

HERE = Path(__file__).resolve().parent
RELEASE = "helm/default/st8-demo"
MESSAGE = "config/default/st8-demo-config/message"
REPLICAS = "deployment/default/st8-demo/replicas"
BASELINE = {
    RELEASE: {"chart": "examples/kind/chart", "version": "0.1.0"},
    MESSAGE: "hello from st8",
    REPLICAS: 1,
}


def main() -> None:
    for filename, initial in (
        ("install.yaml", {}),
        ("changes.yaml", BASELINE),
        ("destructive.yaml", BASELINE),
    ):
        plan = load_plan(HERE / filename)
        result = preview(plan, initial)
        print(f"\n{plan.name}")
        print(f"  initial: {state_hash(result.initial_state)}")
        for step in result.steps:
            print(f"  {step.id}: {step.before_hash} -> {step.after_hash}")
            if step.snapshot:
                print(f"    snapshot requirement: {step.snapshot}")
        for step in result.recovery:
            print(f"  recovery: {step.step_id}: {step.command} {step.target} {step.value!r}")
        print(f"  recovery complete: {result.recovery_complete}")


if __name__ == "__main__":
    main()
