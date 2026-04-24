from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunReport:
    flow: str
    report_out: Path
    status: str = "running"
    started_at: str = field(default_factory=utc_now)
    ended_at: str | None = None
    steps: list[dict[str, Any]] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] | None = None

    def add_step(self, result: dict[str, Any]) -> None:
        self.steps.append(result)

    def finish(self, status: str, error: dict[str, Any] | None = None) -> "RunReport":
        self.status = status
        self.ended_at = utc_now()
        self.error = error
        self.write()
        return self

    def write(self) -> None:
        self.report_out.parent.mkdir(parents=True, exist_ok=True)
        self.report_out.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def to_dict(self) -> dict[str, Any]:
        data = {
            "flow": self.flow,
            "status": self.status,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "steps": self.steps,
            "artifacts": self.artifacts,
        }
        if self.error:
            data["error"] = self.error
        return data
