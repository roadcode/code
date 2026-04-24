from __future__ import annotations

import time
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
        attached_pages: set[Any] = set()
        recorded_new_pages: set[Any] = set()

        def attach_page(target_page: Any) -> None:
            if target_page in attached_pages:
                return
            attached_pages.add(target_page)
            monitor.attach(target_page)

        attach_page(page)

        def on_record(source: Any, payload: dict[str, Any]) -> None:
            payload.setdefault("url", source.get("page").url if isinstance(source, dict) and source.get("page") else page.url)
            payload.setdefault("network_events", [])
            builder.add_event(payload)

        context.expose_binding("__rpa_record", on_record)
        context.add_init_script(path=str(script_path))

        def record_new_page(target_page: Any) -> None:
            if target_page in recorded_new_pages:
                return
            recorded_new_pages.add(target_page)
            builder.add_event(
                {
                    "type": "new_page",
                    "ts": time.time(),
                    "url": target_page.url,
                    "network_events": [],
                }
            )

        def on_new_page(target_page: Any) -> None:
            attach_page(target_page)
            target_page.once("domcontentloaded", lambda: record_new_page(target_page))
            if target_page.url and target_page.url != "about:blank":
                record_new_page(target_page)

        context.on("page", on_new_page)
        page.goto(args.url, wait_until="domcontentloaded")
        print("Recording started. Close the browser window or press Ctrl+C to stop.")
        try:
            page.wait_for_event("close", timeout=0)
        except KeyboardInterrupt:
            pass
        flow = builder.to_flow()
        write_flow(out, flow)
        context.close()
        return flow
