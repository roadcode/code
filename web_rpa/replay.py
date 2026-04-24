from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from .browser import launch_replay_browser, maybe_start_trace, maybe_stop_trace
from .errors import SelectorAmbiguous, SelectorNotFound, WebRpaError
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
            signature = submit_click_signature(step)
            if signature is not None and signature == last_submit_click_signature:
                report.add_step(step_result(step, "skipped", start, reason="duplicate submit click"))
                index += 1
                continue
            action = build_action(current_page, resolver, step)
            result = wait_manager.run_action_with_waits(current_page, step, action)
            if step.get("type") == "new_page" and result is not None:
                current_page = result
                resolver = LocatorResolver(current_page)
            report.add_step(step_result(step, "passed", start))
            last_submit_click_signature = signature
            index += 1
        except Exception as exc:
            resume_index = find_resumable_step(current_page, steps, index + 1)
            if isinstance(exc, (SelectorNotFound, SelectorAmbiguous)) and resume_index is not None:
                report.add_step(step_result(step, "skipped", start, reason="target unavailable; later step already available"))
                for skipped in steps[index + 1 : resume_index]:
                    report.add_step(step_result(skipped, "skipped", time.perf_counter(), reason="covered by later available step"))
                index = resume_index
                continue
            result = step_result(step, "failed", start)
            result.update(error_payload(exc, page))
            if isinstance(exc, WebRpaError) and exc.details.get("tried"):
                result["locator_tried"] = exc.details["tried"]
            result["step"] = step
            report.add_step(result)
            raise


def find_resumable_step(page: Any, steps: list[dict[str, Any]], start_index: int) -> int | None:
    probe = LocatorResolver(page, timeout_ms=0)
    failed_url = steps[start_index - 1].get("url") if start_index > 0 else None
    for index in range(start_index, len(steps)):
        step = steps[index]
        if failed_url and step.get("url") != failed_url:
            continue
        if step.get("type") == "goto" or not step.get("target"):
            continue
        try:
            probe.resolve(step["target"])
            return index
        except (SelectorNotFound, SelectorAmbiguous):
            continue
    return None


def build_action(page: Any, resolver: LocatorResolver, step: dict[str, Any]):
    step_type = step["type"]
    if step_type == "goto":
        return lambda: page.goto(step["url"], wait_until=(step.get("wait") or {}).get("state", "domcontentloaded"))
    if step_type == "new_page":
        def open_new_page():
            new_page = page.context.new_page()
            new_page.goto(step["url"], wait_until=(step.get("wait") or {}).get("state", "domcontentloaded"))
            return new_page

        return open_new_page
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
