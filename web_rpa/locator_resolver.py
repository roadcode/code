from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .errors import SelectorAmbiguous, SelectorNotFound


@dataclass
class LocatorResolution:
    locator: Any
    candidate: dict[str, Any]
    tried: list[dict[str, Any]] = field(default_factory=list)


class LocatorResolver:
    def __init__(self, page: Any):
        self.page = page

    def materialize(self, candidate: dict[str, Any]):
        kind = candidate.get("kind")
        if kind == "test_id":
            return self.page.get_by_test_id(candidate["value"])
        if kind == "role":
            return self.page.get_by_role(candidate["role"], name=candidate.get("name"))
        if kind == "label":
            return self.page.get_by_label(candidate["value"])
        if kind == "placeholder":
            return self.page.get_by_placeholder(candidate["value"])
        if kind == "text":
            return self.page.get_by_text(candidate["value"])
        if kind == "css":
            return self.page.locator(candidate["value"])
        if kind == "xpath":
            return self.page.locator("xpath=" + candidate["value"])
        if kind == "title":
            return self.page.locator(f"[title={css_string(candidate['value'])}]")
        if kind == "alt":
            return self.page.locator(f"[alt={css_string(candidate['value'])}]")
        return self.page.locator(candidate.get("value", ""))

    def resolve(self, target: dict[str, Any]) -> LocatorResolution:
        candidates = [target.get("primary"), *(target.get("candidates") or [])]
        tried: list[dict[str, Any]] = []
        ambiguous: list[dict[str, Any]] = []
        for candidate in filter(None, candidates):
            locator = self.materialize(candidate)
            try:
                count = locator.count()
            except Exception as exc:
                tried.append({**candidate, "result": f"error: {exc}"})
                continue
            if count == 0:
                tried.append({**candidate, "result": "0 matches"})
                continue
            if count > 1:
                result = {**candidate, "result": f"{count} matches"}
                tried.append(result)
                ambiguous.append(result)
                continue
            try:
                if not locator.is_visible():
                    tried.append({**candidate, "result": "1 match but not visible"})
                    continue
            except Exception:
                pass
            tried.append({**candidate, "result": "1 match"})
            return LocatorResolution(locator=locator, candidate=candidate, tried=tried)
        if ambiguous:
            raise SelectorAmbiguous("selector 匹配多个元素", details={"tried": tried})
        raise SelectorNotFound("selector 未找到可操作元素", details={"tried": tried})


def css_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
