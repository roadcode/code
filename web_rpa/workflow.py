from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .flow import FLOW_VERSION, FlowStep
from .network_monitor import infer_wait_after
from .selector_builder import build_target


FILL_MERGE_WINDOW_SECONDS = 0.5


@dataclass
class WorkflowBuilder:
    name: str
    initial_url: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    last_event_ts: float = 0

    def __post_init__(self) -> None:
        self.steps.append(
            FlowStep(
                id=self.next_id(),
                type="goto",
                url=self.initial_url,
                wait={"kind": "page", "state": "domcontentloaded"},
            ).to_dict()
        )

    def next_id(self) -> str:
        return f"s{len(self.steps) + 1}"

    def add_event(self, event: dict[str, Any]) -> None:
        step = self.event_to_step(event)
        if not step:
            return
        ts = event.get("ts") or time.time()
        if self.should_merge_fill(step, event, ts):
            self.steps[-1]["value"] = step["value"]
            self.steps[-1]["network_events"] = event.get("network_events", [])
            self.last_event_ts = ts
            return
        self.steps.append(step)
        self.last_event_ts = ts

    def event_to_step(self, event: dict[str, Any]) -> dict[str, Any] | None:
        event_type = event.get("type")
        descriptor = event.get("descriptor") or {}
        target = build_target(descriptor) if descriptor else None
        if event_type == "click":
            return self.action_step("click", target, event)
        if event_type == "fill":
            step = self.action_step("fill", target, event)
            step["value"] = event.get("value", "")
            return step
        if event_type in {"select", "change"}:
            step = self.action_step(event_type, target, event)
            step["value"] = event.get("value", "")
            return step
        if event_type == "press" and event.get("key") == "Enter":
            step = self.action_step("press", target, event)
            step["key"] = "Enter"
            return step
        return None

    def action_step(self, step_type: str, target: dict[str, Any] | None, event: dict[str, Any]) -> dict[str, Any]:
        before_url = event.get("before_url") or event.get("url") or self.initial_url
        after_url = event.get("after_url") or event.get("url") or before_url
        return FlowStep(
            id=self.next_id(),
            type=step_type,
            url=after_url,
            target=target,
            wait_after=infer_wait_after(before_url, after_url, event.get("network_events") or []),
            network_events=event.get("network_events") or [],
        ).to_dict()

    def should_merge_fill(self, step: dict[str, Any], event: dict[str, Any], ts: float) -> bool:
        if not self.steps or step.get("type") != "fill" or self.steps[-1].get("type") != "fill":
            return False
        if ts - self.last_event_ts > FILL_MERGE_WINDOW_SECONDS:
            return False
        previous = self.steps[-1].get("target", {}).get("fingerprint")
        current = step.get("target", {}).get("fingerprint")
        return previous == current and step.get("url") == self.steps[-1].get("url")

    def to_flow(self) -> dict[str, Any]:
        return {"version": FLOW_VERSION, "name": self.name, "steps": self.steps}
