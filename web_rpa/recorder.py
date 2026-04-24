from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from .browser import launch_recording_context
from .flow import write_flow
from .network_monitor import NetworkMonitor
from .workflow import WorkflowBuilder


def record_flow(args: Any) -> dict[str, Any]:
    out = Path(args.out)
    flow_name = args.name or out.stem
    builder = WorkflowBuilder(name=flow_name, initial_url=args.url)
    script_path = Path(__file__).with_name("injected_recorder.js")

    with sync_playwright() as p:
        context = launch_recording_context(p, args.profile, browser=args.browser)
        page = context.pages[0] if context.pages else context.new_page()
        monitor = NetworkMonitor()
        monitor.attach(page)

        def on_record(source: Any, payload: dict[str, Any]) -> None:
            payload.setdefault("url", source.get("page").url if isinstance(source, dict) and source.get("page") else page.url)
            payload.setdefault("network_events", [])
            builder.add_event(payload)

        context.expose_binding("__rpa_record", on_record)
        context.add_init_script(path=str(script_path))
        page.goto(args.url, wait_until="domcontentloaded")
        print("Recording started. Close the browser window or press Ctrl+C to stop.")
        try:
            page.wait_for_event("close", timeout=0)
        except KeyboardInterrupt:
            pass
        finally:
            flow = builder.to_flow()
            write_flow(out, flow)
            context.close()
            return flow
