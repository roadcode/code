from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import InvalidFlow, MissingVariable


FLOW_VERSION = "0.1"
SUPPORTED_STEPS = {"goto", "new_page", "click", "fill", "select", "change", "press"}
SUPPORTED_WAITS = {"none", "page", "response", "url", "locator_visible", "locator_hidden", "composite"}
SUPPORTED_LOCATORS = {"test_id", "role", "label", "placeholder", "title", "alt", "text", "css", "xpath"}
VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass
class LocatorCandidate:
    kind: str
    value: str | None = None
    role: str | None = None
    name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class Target:
    primary: dict[str, Any]
    candidates: list[dict[str, Any]] = field(default_factory=list)
    fingerprint: dict[str, Any] = field(default_factory=dict)
    frame: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "primary": self.primary,
            "candidates": self.candidates,
            "fingerprint": self.fingerprint,
        }
        if self.frame:
            data["frame"] = self.frame
        return data


@dataclass
class FlowStep:
    id: str
    type: str
    url: str | None = None
    value: str | None = None
    key: str | None = None
    target: Target | dict[str, Any] | None = None
    wait: dict[str, Any] | None = None
    wait_after: dict[str, Any] = field(default_factory=lambda: {"kind": "none"})
    network_events: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"id": self.id, "type": self.type}
        for key in ("url", "value", "key", "wait", "wait_after", "network_events"):
            value = getattr(self, key)
            if value not in (None, [], {}):
                data[key] = value
        if self.target is not None:
            data["target"] = self.target.to_dict() if isinstance(self.target, Target) else self.target
        return data


@dataclass
class Flow:
    name: str
    steps: list[dict[str, Any]]
    version: str = FLOW_VERSION
    reports: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = {"version": self.version, "name": self.name, "steps": self.steps}
        if self.reports:
            data["reports"] = self.reports
        return data


def read_flow(path: Path | str) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InvalidFlow(f"flow JSON 无法解析：{exc}") from exc
    validate_flow(data)
    return data


def write_flow(path: Path | str, flow: dict[str, Any] | Flow) -> None:
    output = flow.to_dict() if isinstance(flow, Flow) else flow
    validate_flow(output)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_vars(path: Path | str | None) -> dict[str, Any]:
    if not path:
        return {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InvalidFlow(f"vars 文件必须是 JSON：{exc}") from exc


def substitute_vars(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, str):
        def repl(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in variables:
                raise MissingVariable(f"变量 `{name}` 未在 vars 文件中提供")
            return str(variables[name])

        return VAR_PATTERN.sub(repl, value)
    if isinstance(value, list):
        return [substitute_vars(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: substitute_vars(item, variables) for key, item in value.items()}
    return value


def materialize_flow(flow: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    copied = copy.deepcopy(flow)
    copied["steps"] = [substitute_vars(step, variables) for step in copied.get("steps", [])]
    validate_flow(copied)
    return copied


def validate_flow(flow: dict[str, Any]) -> None:
    if not isinstance(flow, dict):
        raise InvalidFlow("flow 必须是 JSON object")
    if not flow.get("version"):
        raise InvalidFlow("flow 缺少 version")
    if not flow.get("name"):
        raise InvalidFlow("flow 缺少 name")
    steps = flow.get("steps")
    if not isinstance(steps, list):
        raise InvalidFlow("flow 缺少 steps 数组")
    for index, step in enumerate(steps, start=1):
        validate_step(step, index)


def validate_step(step: dict[str, Any], index: int) -> None:
    if not isinstance(step, dict):
        raise InvalidFlow(f"step {index} 必须是 object")
    step_type = step.get("type")
    if not step.get("id") or step_type not in SUPPORTED_STEPS:
        raise InvalidFlow(f"step {index} 缺少 id 或包含不支持的 type")
    if step_type in {"goto", "new_page"} and not step.get("url"):
        raise InvalidFlow(f"{step_type} step {index} 缺少 url")
    if step_type not in {"goto", "new_page"}:
        validate_target(step.get("target"), index)
    if step_type in {"fill", "select", "change"} and "value" not in step:
        raise InvalidFlow(f"{step_type} step {index} 缺少 value")
    if step_type == "press" and not step.get("key"):
        raise InvalidFlow(f"press step {index} 缺少 key")
    for wait_key in ("wait", "wait_after"):
        if wait_key in step:
            validate_wait(step[wait_key], f"step {index} {wait_key}")


def validate_target(target: Any, index: int) -> None:
    if not isinstance(target, dict):
        raise InvalidFlow(f"step {index} 缺少 target")
    if "primary" not in target or "candidates" not in target or "fingerprint" not in target:
        raise InvalidFlow(f"step {index} target 必须包含 primary/candidates/fingerprint")
    validate_locator(target["primary"], f"step {index} primary")
    if not isinstance(target["candidates"], list):
        raise InvalidFlow(f"step {index} candidates 必须是数组")
    for candidate in target["candidates"]:
        validate_locator(candidate, f"step {index} candidate")


def validate_locator(locator: Any, where: str) -> None:
    if not isinstance(locator, dict) or locator.get("kind") not in SUPPORTED_LOCATORS:
        raise InvalidFlow(f"{where} locator kind 不受支持")
    if locator["kind"] == "role":
        if not locator.get("role"):
            raise InvalidFlow(f"{where} role locator 缺少 role")
    elif not locator.get("value"):
        raise InvalidFlow(f"{where} locator 缺少 value")


def validate_wait(wait: Any, where: str) -> None:
    if not isinstance(wait, dict) or wait.get("kind") not in SUPPORTED_WAITS:
        raise InvalidFlow(f"{where} wait kind 不受支持")
    if wait["kind"] == "composite":
        if wait.get("mode") not in {"any", "all"}:
            raise InvalidFlow(f"{where} composite wait mode 必须是 any 或 all")
        for item in wait.get("items", []):
            validate_wait(item, where)
