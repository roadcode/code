from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any

from .errors import SelectorAmbiguous, SelectorNotFound


TEXT_ALIASES = {
    "查询": ["搜索"],
    "搜索": ["查询"],
}


@dataclass
class LocatorResolution:
    locator: Any
    candidate: dict[str, Any]
    tried: list[dict[str, Any]] = field(default_factory=list)


class LocatorResolver:
    def __init__(self, page: Any, *, timeout_ms: int = 15000):
        self.page = page
        self.timeout_ms = timeout_ms

    def materialize(self, candidate: dict[str, Any]):
        return self._materialize_in(self.page, candidate)

    def _materialize_in(self, scope: Any, candidate: dict[str, Any]):
        kind = candidate.get("kind")
        if kind == "test_id":
            return scope.get_by_test_id(candidate["value"])
        if kind == "role":
            return scope.get_by_role(candidate["role"], name=candidate.get("name"))
        if kind == "label":
            return scope.get_by_label(candidate["value"])
        if kind == "placeholder":
            return scope.get_by_placeholder(candidate["value"])
        if kind == "text":
            return scope.get_by_text(candidate["value"])
        if kind == "css":
            return scope.locator(candidate["value"])
        if kind == "xpath":
            return scope.locator("xpath=" + candidate["value"])
        if kind == "title":
            return scope.locator(f"[title={css_string(candidate['value'])}]")
        if kind == "alt":
            return scope.locator(f"[alt={css_string(candidate['value'])}]")
        return scope.locator(candidate.get("value", ""))

    def resolve(self, target: dict[str, Any]) -> LocatorResolution:
        candidates = self._ordered_candidates(target)
        fingerprint = target.get("fingerprint")
        tried: list[dict[str, Any]] = []
        ambiguous: list[dict[str, Any]] = []
        deadline = time.monotonic() + self.timeout_ms / 1000
        while True:
            pending: list[dict[str, Any]] = []
            for candidate in filter(None, candidates):
                resolution = self._try_candidate_across_scopes(candidate, fingerprint)
                if resolution["status"] == "resolved":
                    tried.extend(resolution["tried"])
                    return LocatorResolution(locator=resolution["locator"], candidate=candidate, tried=tried)
                tried.extend(resolution["tried"])
                if resolution["status"] == "pending":
                    pending.append(candidate)
                elif resolution["status"] == "ambiguous":
                    ambiguous.extend(resolution["tried"])
            if time.monotonic() >= deadline or not pending:
                break
            tried.clear()
            time.sleep(0.1)
        if ambiguous:
            raise SelectorAmbiguous("selector 匹配多个元素", details={"tried": tried or ambiguous})
        raise SelectorNotFound("selector 未找到可操作元素", details={"tried": tried})

    def _try_candidate_across_scopes(self, candidate: dict[str, Any], fingerprint: dict[str, Any] | None) -> dict[str, Any]:
        tried: list[dict[str, Any]] = []
        pending = False
        ambiguous = False
        for scope_name, scope in self._scopes():
            locator = self._materialize_in(scope, candidate)
            resolution = self._try_candidate(scope, locator, candidate, fingerprint)
            tried_item = resolution["tried"]
            if scope_name:
                tried_item = {**tried_item, "frame": scope_name}
            if resolution["status"] == "resolved":
                return {"status": "resolved", "locator": resolution["locator"], "tried": [tried_item]}
            tried.append(tried_item)
            pending = pending or resolution["status"] == "pending"
            ambiguous = ambiguous or resolution["status"] == "ambiguous"
        return {"status": "pending" if pending else "ambiguous" if ambiguous else "error", "tried": tried}

    def _scopes(self) -> list[tuple[str | None, Any]]:
        scopes: list[tuple[str | None, Any]] = [(None, self.page)]
        main_frame = getattr(self.page, "main_frame", None)
        for index, frame in enumerate(getattr(self.page, "frames", []) or []):
            if frame is main_frame:
                continue
            scopes.append((getattr(frame, "url", None) or f"frame[{index}]", frame))
        return scopes

    def _try_candidate(self, scope: Any, locator: Any, candidate: dict[str, Any], fingerprint: dict[str, Any] | None) -> dict[str, Any]:
        try:
            count = locator.count()
        except Exception as exc:
            return {"status": "error", "tried": {**candidate, "result": f"error: {exc}"}}
        if count == 0:
            return {"status": "pending", "tried": {**candidate, "result": "0 matches"}}
        if count > 1:
            narrowed = self._narrow_by_fingerprint(scope, locator, fingerprint, count)
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
            for alias in self._text_aliases(candidate):
                alias_key = tuple(sorted(alias.items()))
                if alias_key not in seen:
                    seen.add(alias_key)
                    ordered.append(alias)
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
        if candidate.get("kind") == "text" and candidate.get("alias_for"):
            return 5
        if candidate.get("kind") == "text":
            return 6
        if candidate.get("kind") == "xpath":
            return 7
        return 8

    def _text_aliases(self, candidate: dict[str, Any]) -> list[dict[str, Any]]:
        if candidate.get("kind") != "text":
            return []
        return [{"kind": "text", "value": alias, "alias_for": candidate.get("value")} for alias in TEXT_ALIASES.get(candidate.get("value"), [])]

    def _narrow_by_fingerprint(self, scope: Any, locator: Any, fingerprint: dict[str, Any] | None, count: int):
        if not fingerprint or not fingerprint.get("href"):
            return self._narrow_by_bbox(locator, fingerprint, count)
        href_locator = scope.locator(f'a[href={css_string(fingerprint["href"])}]')
        try:
            if href_locator.count() == 1 and href_locator.is_visible():
                return href_locator
        except Exception:
            pass
        return self._narrow_by_bbox(locator, fingerprint, count)

    def _narrow_by_bbox(self, locator: Any, fingerprint: dict[str, Any] | None, count: int):
        bbox = (fingerprint or {}).get("bbox")
        if not bbox or count <= 1 or count > 20:
            return None
        target_center = (bbox.get("x", 0) + bbox.get("w", 0) / 2, bbox.get("y", 0) + bbox.get("h", 0) / 2)
        best = None
        best_distance = None
        for index in range(count):
            candidate = locator.nth(index)
            try:
                if not candidate.is_visible():
                    continue
                candidate_box = candidate.bounding_box()
            except Exception:
                continue
            if not candidate_box:
                continue
            center = (
                candidate_box.get("x", 0) + candidate_box.get("width", candidate_box.get("w", 0)) / 2,
                candidate_box.get("y", 0) + candidate_box.get("height", candidate_box.get("h", 0)) / 2,
            )
            distance = (center[0] - target_center[0]) ** 2 + (center[1] - target_center[1]) ** 2
            if best_distance is None or distance < best_distance:
                best = candidate
                best_distance = distance
        return best


def css_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
