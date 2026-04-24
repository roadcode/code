from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any

from .errors import SelectorAmbiguous, SelectorNotFound


@dataclass
class LocatorResolution:
    locator: Any
    candidate: dict[str, Any]
    tried: list[dict[str, Any]] = field(default_factory=list)


class LocatorResolver:
    def __init__(self, page: Any, *, timeout_ms: int = 5000):
        self.page = page
        self.timeout_ms = timeout_ms

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
        candidates = self._ordered_candidates(target)
        fingerprint = target.get("fingerprint")
        tried: list[dict[str, Any]] = []
        ambiguous: list[dict[str, Any]] = []
        deadline = time.monotonic() + self.timeout_ms / 1000
        while True:
            pending: list[dict[str, Any]] = []
            for candidate in filter(None, candidates):
                locator = self.materialize(candidate)
                resolution = self._try_candidate(locator, candidate, fingerprint)
                if resolution["status"] == "resolved":
                    tried.append(resolution["tried"])
                    return LocatorResolution(locator=resolution["locator"], candidate=candidate, tried=tried)
                tried.append(resolution["tried"])
                if resolution["status"] == "pending":
                    pending.append(candidate)
                elif resolution["status"] == "ambiguous":
                    ambiguous.append(resolution["tried"])
            if time.monotonic() >= deadline or not pending:
                break
            tried.clear()
            time.sleep(0.1)
        if ambiguous:
            raise SelectorAmbiguous("selector 匹配多个元素", details={"tried": tried or ambiguous})
        raise SelectorNotFound("selector 未找到可操作元素", details={"tried": tried})

    def _try_candidate(self, locator: Any, candidate: dict[str, Any], fingerprint: dict[str, Any] | None) -> dict[str, Any]:
        try:
            count = locator.count()
        except Exception as exc:
            return {"status": "error", "tried": {**candidate, "result": f"error: {exc}"}}
        if count == 0:
            return {"status": "pending", "tried": {**candidate, "result": "0 matches"}}
        if count > 1:
            narrowed = self._narrow_by_fingerprint(fingerprint)
            if narrowed is not None:
                return {"status": "resolved", "locator": narrowed, "tried": {**candidate, "result": "narrowed via fingerprint"}}
            return {"status": "ambiguous", "tried": {**candidate, "result": f"{count} matches"}}
        try:
            if not locator.is_visible():
                return {"status": "pending", "tried": {**candidate, "result": "1 match but not visible"}}
        except Exception:
            pass
        return {"status": "resolved", "locator": locator, "tried": {**candidate, "result": "1 match"}}

    def _ordered_candidates(self, target: dict[str, Any]) -> list[dict[str, Any]]:
        raw = [target.get("primary"), *(target.get("candidates") or [])]
        fingerprint = target.get("fingerprint") or {}
        href = fingerprint.get("href")
        if href:
            raw.insert(0, {"kind": "css", "value": f'a[href={css_string(href)}]'})
        seen: set[tuple] = set()
        ordered: list[dict[str, Any]] = []
        for candidate in raw:
            if not candidate:
                continue
            key = tuple(sorted(candidate.items()))
            if key not in seen:
                seen.add(key)
                ordered.append(candidate)
        primary = ordered[:1]
        rest = sorted(ordered[1:], key=self._candidate_score)
        return primary + rest

    def _candidate_score(self, candidate: dict[str, Any]) -> int:
        value = candidate.get("value") or ""
        if candidate.get("kind") == "test_id":
            return 0
        if candidate.get("kind") == "css" and "href=" in value:
            return 1
        if candidate.get("kind") == "css" and any(attr in value for attr in ("data-testid", "data-test", "data-qa", "data-cy", "name=", "aria-label")):
            return 2
        if candidate.get("kind") in {"role", "label", "placeholder"}:
            return 3
        if candidate.get("kind") in {"title", "alt"}:
            return 4
        if candidate.get("kind") == "css":
            return 5
        if candidate.get("kind") == "text":
            return 6
        if candidate.get("kind") == "xpath":
            return 7
        return 8

    def _narrow_by_fingerprint(self, fingerprint: dict[str, Any] | None):
        if not fingerprint or not fingerprint.get("href"):
            return None
        narrowed = self.page.locator(f'a[href={css_string(fingerprint["href"])}]')
        try:
            if narrowed.count() == 1 and narrowed.is_visible():
                return narrowed
        except Exception:
            return None
        return None


def css_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
