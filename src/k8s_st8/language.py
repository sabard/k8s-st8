"""Strict parsing and validation of version 1 state plans."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class LanguageError(ValueError):
    """A plan or projected state is invalid."""


class _UniqueLoader(yaml.SafeLoader):
    pass


def _mapping(loader: _UniqueLoader, node: yaml.MappingNode) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str):
            raise LanguageError("YAML mapping keys must be strings")
        if key in result:
            raise LanguageError(f"duplicate YAML key: {key!r}")
        result[key] = loader.construct_object(value_node)
    return result


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def _json_value(value: Any, where: str, active: set[int] | None = None) -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        import math

        if math.isfinite(value):
            return
    if isinstance(value, (list, dict)):
        active = active if active is not None else set()
        if id(value) in active:
            raise LanguageError(f"{where} contains a recursive value")
        active.add(id(value))
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str):
                    raise LanguageError(f"{where} must have string keys")
                _json_value(item, where, active)
        else:
            for item in value:
                _json_value(item, where, active)
        active.remove(id(value))
        return
    raise LanguageError(f"{where} must contain only finite JSON values")


def _fields(value: Any, required: set[str], optional: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LanguageError(f"{where} must be a mapping")
    missing = required - value.keys()
    extra = value.keys() - required - optional
    if missing or extra:
        raise LanguageError(f"{where}: missing fields {sorted(missing)}, unknown fields {sorted(extra)}")
    return value


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LanguageError(f"{where} must be a non-empty string")
    return value


@dataclass(frozen=True)
class Step:
    id: str
    command: str
    depends_on: tuple[str, ...]
    recovery: str
    impact: tuple[str, ...]
    target: str | None = None
    value: Any = None
    undo: str | None = None
    snapshot: str | None = None


@dataclass(frozen=True)
class Plan:
    name: str
    steps: tuple[Step, ...]


def parse_plan(source: str) -> Plan:
    """Parse a YAML plan and validate its dependency graph and recovery contracts."""
    try:
        raw = yaml.load(source, Loader=_UniqueLoader)
    except yaml.YAMLError as exc:
        raise LanguageError(f"invalid YAML: {exc}") from exc
    root = _fields(raw, {"version", "name", "steps"}, set(), "plan")
    if type(root["version"]) is not int or root["version"] != 1:
        raise LanguageError("version must be 1")
    name = _text(root["name"], "plan name")
    if not isinstance(root["steps"], list):
        raise LanguageError("steps must be a list")
    steps: list[Step] = []
    for index, raw_step in enumerate(root["steps"]):
        where = f"step {index + 1}"
        item = _fields(raw_step, {"id", "command", "recovery", "impact"},
                       {"depends_on", "target", "value", "undo", "snapshot"}, where)
        step_id = _text(item["id"], f"{where} id")
        command = _text(item["command"], f"{where} command")
        if command not in {"set", "delete", "action"}:
            raise LanguageError(f"{where}: unknown command {command!r}")
        recovery = _text(item["recovery"], f"{where} recovery")
        if recovery not in {"reversible", "compensatable", "irreversible"}:
            raise LanguageError(f"{where}: invalid recovery {recovery!r}")
        impact = item["impact"]
        allowed_impacts = {"workload", "configuration", "persistent_data", "infrastructure", "traffic"}
        if not isinstance(impact, list) or not impact or any(
            not isinstance(i, str) or i not in allowed_impacts for i in impact
        ) or len(set(impact)) != len(impact):
            raise LanguageError(f"{where}: impact must be a non-empty list of distinct known impacts")
        dependencies = item.get("depends_on", [])
        if not isinstance(dependencies, list) or any(
            not isinstance(dep, str) or not dep.strip() for dep in dependencies
        ) or len(set(dependencies)) != len(dependencies):
            raise LanguageError(f"{where}: depends_on must be a list of distinct step IDs")
        target = _text(item["target"], f"{where} target") if "target" in item else None
        undo = _text(item["undo"], f"{where} undo") if "undo" in item else None
        snapshot = _text(item["snapshot"], f"{where} snapshot") if "snapshot" in item else None
        if command in {"set", "delete"} and target is None:
            raise LanguageError(f"{where}: {command} requires target")
        if command == "set":
            if "value" not in item:
                raise LanguageError(f"{where}: set requires value")
            _json_value(item["value"], f"{where} value")
        elif "value" in item:
            raise LanguageError(f"{where}: {command} does not accept value")
        if command == "action" and target is None:
            raise LanguageError(f"{where}: action requires a target describing the action")
        if command == "action" and recovery != "irreversible" and undo is None:
            raise LanguageError(f"{where}: an action needs an explicit undo or compensation")
        if recovery == "irreversible" and snapshot is None:
            raise LanguageError(f"{where}: irreversible steps require a snapshot requirement")
        if recovery == "irreversible" and undo is not None:
            raise LanguageError(f"{where}: irreversible steps cannot declare undo")
        steps.append(Step(step_id, command, tuple(dependencies), recovery, tuple(impact),
                          target, item.get("value"), undo, snapshot))
    plan = Plan(name, tuple(steps))
    ordered_steps(plan)
    return plan


def load_plan(path: str | Path) -> Plan:
    return parse_plan(Path(path).read_text(encoding="utf-8"))


def ordered_steps(plan: Plan) -> tuple[Step, ...]:
    by_id = {step.id: step for step in plan.steps}
    if len(by_id) != len(plan.steps):
        raise LanguageError("step IDs must be unique")
    for step in plan.steps:
        for dependency in step.depends_on:
            if dependency not in by_id:
                raise LanguageError(f"step {step.id!r} depends on unknown step {dependency!r}")
    ordered: list[Step] = []
    done: set[str] = set()
    while len(done) < len(plan.steps):
        ready = next((step for step in plan.steps
                      if step.id not in done and set(step.depends_on) <= done), None)
        if ready is None:
            raise LanguageError("dependency graph contains a cycle")
        ordered.append(ready)
        done.add(ready.id)
    return tuple(ordered)
