from __future__ import annotations

from typing import Any, Callable

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from .errors import WaitTimeout
from .locator_resolver import LocatorResolver


Action = Callable[[], Any]


class WaitManager:
    def __init__(self, resolver_factory=LocatorResolver):
        self.resolver_factory = resolver_factory

    def run_action_with_waits(self, page: Any, step: dict[str, Any], action_callable: Action) -> Any:
        wait = step.get("wait_after") or {"kind": "none"}
        return self._run_wait(page, wait, action_callable)

    def _run_wait(self, page: Any, wait: dict[str, Any], action_callable: Action) -> Any:
        kind = wait.get("kind", "none")
        timeout = wait.get("timeout", 30000)
        try:
            if kind in {"none", "page"}:
                return action_callable()
            if kind == "response":
                predicate = response_predicate(wait)
                with page.expect_response(predicate, timeout=timeout):
                    return action_callable()
            result = action_callable()
            if kind == "url":
                page.wait_for_url(wait["pattern"], timeout=timeout)
            elif kind in {"locator_visible", "locator_hidden"}:
                locator_spec = wait.get("locator") or wait.get("target")
                locator = self.resolver_factory(page).materialize(locator_spec)
                state = "visible" if kind == "locator_visible" else "hidden"
                locator.wait_for(state=state, timeout=timeout)
            elif kind == "composite":
                self._run_composite(page, wait)
            else:
                raise WaitTimeout(f"不支持的 wait kind：{kind}", details={"wait": wait})
            return result
        except WaitTimeout:
            raise
        except PlaywrightTimeoutError as exc:
            raise WaitTimeout(f"等待失败：{kind}", details={"wait": wait, "error": str(exc)}) from exc

    def _run_composite(self, page: Any, wait: dict[str, Any]) -> None:
        items = wait.get("items") or []
        mode = wait.get("mode", "all")
        errors: list[str] = []
        for item in items:
            try:
                self._run_wait(page, item, lambda: None)
                if mode == "any":
                    return
            except WaitTimeout as exc:
                errors.append(str(exc))
                if mode == "all":
                    raise WaitTimeout("复合等待失败", details={"wait": item, "errors": errors}) from exc
        if mode == "any" and errors:
            raise WaitTimeout("复合等待任一条件均未满足", details={"wait": wait, "errors": errors})


def response_predicate(wait: dict[str, Any]):
    method = wait.get("method")
    pattern = wait.get("url_pattern") or wait.get("pattern")
    statuses = set(wait.get("status") or [])

    def predicate(response: Any) -> bool:
        request = response.request
        if method and request.method.upper() != method.upper():
            return False
        if statuses and response.status not in statuses:
            return False
        if pattern and not url_matches(pattern, response.url):
            return False
        return True

    return predicate


def url_matches(pattern: str, url: str) -> bool:
    if pattern.startswith("**"):
        return pattern[2:].rstrip("*") in url
    return pattern.rstrip("*") in url
