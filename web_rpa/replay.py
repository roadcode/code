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
    resolver = LocatorResolver(page)
    wait_manager = WaitManager()
    for step in steps:
        start = time.perf_counter()
        try:
            action = build_action(page, resolver, step)
            wait_manager.run_action_with_waits(page, step, action)
            report.add_step(step_result(step, "passed", start))
        except Exception as exc:
            result = step_result(step, "failed", start)
            result.update(error_payload(exc, page))
            if isinstance(exc, WebRpaError) and exc.details.get("tried"):
                result["locator_tried"] = exc.details["tried"]
            result["step"] = step
            report.add_step(result)
            raise


def build_action(page: Any, resolver: LocatorResolver, step: dict[str, Any]):
    step_type = step["type"]
    if step_type == "goto":
        return lambda: page.goto(step["url"], wait_until=(step.get("wait") or {}).get("state", "domcontentloaded"))
    if step_type == "click":
        return lambda: resolver.resolve(step["target"]).locator.click()
    if step_type == "fill":
        return lambda: resolver.resolve(step["target"]).locator.fill(step.get("value", ""))
    if step_type in {"select", "change"}:
        return lambda: resolver.resolve(step["target"]).locator.select_option(step.get("value", ""))
    if step_type == "press":
        return lambda: resolver.resolve(step["target"]).locator.press(step["key"])
    raise ValueError(f"unsupported step type {step_type}")


def step_result(step: dict[str, Any], status: str, start: float) -> dict[str, Any]:
    return {
        "id": step.get("id"),
        "type": step.get("type"),
        "status": status,
        "duration_ms": round((time.perf_counter() - start) * 1000),
    }


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
