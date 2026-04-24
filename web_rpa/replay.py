from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from .browser import launch_replay_browser, maybe_start_trace, maybe_stop_trace
from .errors import WebRpaError
from .flow import load_vars, materialize_flow, read_flow
from .locator_resolver import LocatorResolver
from .report import RunReport
from .wait_manager import WaitManager


def run_flow(args: Any) -> RunReport:
    flow_path = Path(args.flow)
    report_out = Path(args.report_out)
    report = RunReport(flow=str(flow_path), report_out=report_out)
    flow = materialize_flow(read_flow(flow_path), load_vars(getattr(args, "vars", None)))
    with sync_playwright() as p:
        browser = launch_replay_browser(p, headed=getattr(args, "headed", False), slow_mo=getattr(args, "slow_mo", 0))
        context = browser.new_context()
        trace_path = report_out.parent / "trace.zip"
        maybe_start_trace(context, getattr(args, "trace", False))
        page = context.new_page()
        try:
            execute_steps(page, flow["steps"], report)
            trace = maybe_stop_trace(context, getattr(args, "trace", False), trace_path)
            if trace:
                report.artifacts["trace"] = trace
            context.close()
            browser.close()
            return report.finish("passed")
        except Exception as exc:
            screenshot = capture_failure_screenshot(page, report_out.parent, current_step_id(report))
            if screenshot:
                report.artifacts["screenshot"] = screenshot
                if report.steps and report.steps[-1].get("status") == "failed":
                    report.steps[-1]["screenshot"] = screenshot
            try:
                trace = maybe_stop_trace(context, getattr(args, "trace", False), trace_path)
                if trace:
                    report.artifacts["trace"] = trace
            finally:
                context.close()
                browser.close()
            return report.finish("failed", error=error_payload(exc, page))


def execute_steps(page: Any, steps: list[dict[str, Any]], report: RunReport) -> None:
    current_page = page
    resolver = LocatorResolver(current_page)
    wait_manager = WaitManager()
    last_submit_click_signature: tuple | None = None
    index = 0
    while index < len(steps):
        step = steps[index]
        start = time.perf_counter()
        try:
            if step.get("type") == "new_page":
                report.add_step(step_result(step, "skipped", start, reason="new page already handled by opener"))
                index += 1
                continue
            signature = submit_click_signature(step)
            if signature is not None and signature == last_submit_click_signature:
                report.add_step(step_result(step, "skipped", start, reason="duplicate submit click"))
                index += 1
                continue
            action = build_action(current_page, resolver, step)
            new_page_step = next_new_page_step(steps, index)
            if new_page_step:
                result = wait_manager.run_action_with_waits(
                    current_page,
                    step,
                    lambda: run_action_expecting_popup(current_page, action, new_page_step),
                )
                current_page = result
                resolver = LocatorResolver(current_page)
            else:
                wait_manager.run_action_with_waits(current_page, step, action)
            report.add_step(step_result(step, "passed", start))
            last_submit_click_signature = signature
            if new_page_step:
                report.add_step(step_result(new_page_step, "passed", start))
                index += 2
                continue
            index += 1
        except Exception as exc:
            result = step_result(step, "failed", start)
            result.update(error_payload(exc, page))
            if isinstance(exc, WebRpaError) and exc.details.get("tried"):
                result["locator_tried"] = exc.details["tried"]
            result["step"] = step
            report.add_step(result)
            raise


def next_new_page_step(steps: list[dict[str, Any]], index: int) -> dict[str, Any] | None:
    if index + 1 >= len(steps):
        return None
    candidate = steps[index + 1]
    if candidate.get("type") == "new_page":
        return candidate
    return None


def run_action_expecting_popup(page: Any, action_callable: Any, new_page_step: dict[str, Any]) -> Any:
    wait = new_page_step.get("wait") or {}
    timeout = wait.get("timeout", 30000)
    with page.expect_popup(timeout=timeout) as popup_info:
        action_callable()
    popup = popup_info.value
    state = wait.get("state", "domcontentloaded")
    popup.wait_for_load_state(state, timeout=timeout)
    return popup


def build_action(page: Any, resolver: LocatorResolver, step: dict[str, Any]):
    step_type = step["type"]
    if step_type == "goto":
        return lambda: page.goto(step["url"], wait_until=(step.get("wait") or {}).get("state", "domcontentloaded"))
    if step_type == "new_page":
        return lambda: page
    if step_type == "click":
        return lambda: resolver.resolve(step["target"]).locator.click()
    if step_type == "fill":
        return lambda: resolver.resolve(step["target"]).locator.fill(step.get("value", ""))
    if step_type == "select":
        return lambda: resolver.resolve(step["target"]).locator.select_option(step.get("value", ""))
    if step_type == "change":
        if is_select_target(step.get("target") or {}):
            return lambda: resolver.resolve(step["target"]).locator.select_option(step.get("value", ""))
        return lambda: resolver.resolve(step["target"]).locator.fill(step.get("value", ""))
    if step_type == "press":
        return lambda: resolver.resolve(step["target"]).locator.press(step["key"])
    raise ValueError(f"unsupported step type {step_type}")


def is_select_target(target: dict[str, Any]) -> bool:
    fingerprint = target.get("fingerprint") or {}
    if (fingerprint.get("tag") or "").lower() == "select":
        return True
    primary = target.get("primary") or {}
    candidates = target.get("candidates") or []
    locators = [primary, *candidates]
    return any("select" in (locator.get("value") or "").lower() for locator in locators if locator.get("kind") == "css")


def submit_click_signature(step: dict[str, Any]) -> tuple | None:
    if step.get("type") != "click":
        return None
    target = step.get("target") or {}
    fingerprint = target.get("fingerprint") or {}
    tag = (fingerprint.get("tag") or "").lower()
    input_type = (fingerprint.get("type") or "").lower()
    if input_type != "submit" and tag != "button":
        return None
    primary = target.get("primary") or {}
    candidates = target.get("candidates") or []
    return (
        step.get("url"),
        tag,
        input_type,
        fingerprint.get("id"),
        fingerprint.get("name"),
        tuple(tuple(sorted(locator.items())) for locator in [primary, *candidates]),
    )


def step_result(step: dict[str, Any], status: str, start: float, *, reason: str | None = None) -> dict[str, Any]:
    result = {
        "id": step.get("id"),
        "type": step.get("type"),
        "status": status,
        "duration_ms": round((time.perf_counter() - start) * 1000),
    }
    if reason:
        result["reason"] = reason
    return result


def capture_failure_screenshot(page: Any, out_dir: Path, step_id: str) -> str | None:
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{step_id}_failed.png"
        page.screenshot(path=str(path), full_page=True)
        return str(path)
    except Exception:
        return None


def current_step_id(report: RunReport) -> str:
    if report.steps:
        return str(report.steps[-1].get("id") or "step")
    return "step"


def error_payload(exc: Exception, page: Any) -> dict[str, Any]:
    payload = {"error": exc.__class__.__name__, "message": str(exc)}
    if isinstance(exc, WebRpaError):
        payload["error"] = exc.code
        payload["details"] = exc.details
    try:
        payload["current_url"] = page.url
    except Exception:
        pass
    return payload
