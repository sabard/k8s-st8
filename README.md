# k8s-st8

A lightweight Python library defining a declarative language for describing Kubernetes cluster state transitions in YAML. Operations move the cluster from state to state and define a state graph. The state graph may be reversed for reversible operations. 

## Setup

Install [pyenv](https://github.com/pyenv/pyenv) and
[pyenv-virtualenv](https://github.com/pyenv/pyenv-virtualenv), then run:

```bash
./setup.sh
```

Setup uses Python 3.13 and a pyenv virtualenv named `k8s-st8`. It
compiles `requirements.in` and `requirements-dev.in` into corresponding
`.txt` files via pip-tools. `./update-deps.sh` can be run if new 
dependencies are added. The `.python-version` file selects the 
virtualenv.

## Test

Tests are written using pytest and run from the project route as follows:

```bash
pytest
```

## Language

See [examples/upgrade.yaml](examples/upgrade.yaml). A version 1 document has a
name and an ordered list of steps. Each step has a unique `id`, a `command`,
an explicit `recovery` contract, a nonempty `impact` list, and optional
`depends_on` IDs. Dependencies may refer forward; a stable topological order
uses the earliest ready step in the file. Add dependencies wherever ordering
matters; independent steps have no implied dependency.

For a hands-on Helm installation, reversal, configuration change, and
backup-based recovery on a disposable kind cluster, see the
[kind walkthrough](examples/kind/README.md).

Commands:

* `set` assigns a JSON-compatible `value` to a string `target` in the managed
  state projection. Use a target convention such as `helm/namespace/release`,
  `resource/namespace/kind/name`, or `config/namespace/name/key`. Values can
  describe chart versions, Kubernetes objects, or configuration.
* `delete` removes a target from the projection, including when it is absent.
* `action` describes an operation outside the projection, using `target` as a
  human-readable description, for example a cluster upgrade or migration.

Recovery is an author-declared contract: `reversible`, `compensatable`, or
`irreversible`. It is not inferred or verified. For `set` and `delete`, the
default recovery restores the previous projected value or its absence. An
optional `undo` string overrides this with a human-described recovery action.
Reversible and compensatable `action` steps require an `undo` description.
Irreversible steps require a `snapshot` string describing the prerequisite
backup or snapshot; this is only a declaration, not proof it exists, covers
the effects, or can be restored. An irreversible step cannot declare `undo`.
Impacts are `workload`, `configuration`, `persistent_data`, `infrastructure`,
and `traffic`. Declare all relevant impacts and choose recovery conservatively:
restoring a Helm value or traffic setting need not reverse hooks, requests,
controller behavior, or persistent and external side effects.

## Python API

```python
from k8s_st8 import load_plan, preview, state_hash

plan = load_plan("examples/upgrade.yaml")
result = preview(plan, {"traffic/production/payments": {"version": "v3", "weight_percent": 100}})
for step in result.steps:
    print(step.id, step.before_hash, step.after_hash, step.snapshot)
for step in result.recovery:
    print(step.step_id, step.command, step.target)
print(result.recovery_complete, state_hash(result.final_state))
```

The preview assumes **all** steps succeeded; it is not an execution log and
does not model partial failures. Recovery runs in reverse order and stops at
the first irreversible step, which appears as a `manual` boundary. A complete
recovery list means only that no such boundary was encountered, not that
recovery will succeed. No-op projection changes still appear as steps; an
unchanged hash does not imply an action had no real-world effects.

Hashes are SHA-256 of canonical JSON for the **entire supplied managed-state
projection** (sorted keys, compact UTF-8 JSON); only finite JSON values with
string mapping keys are supported. Equal projections have equal hashes,
including no-op sets/deletes and a projection restored to its prior value.
Hashes are not cluster fingerprints: unmodeled objects, data, side effects,
and drift are invisible. YAML mapping keys must be unique strings, and YAML
values such as timestamps must be quoted to remain JSON-compatible strings.
Plans may contain sensitive values: protect plans, state, and previews
accordingly.
