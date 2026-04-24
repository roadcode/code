from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


STATIC_RESOURCE_TYPES = {"image", "font", "stylesheet", "media", "websocket"}
NOISE_PATTERNS = ("analytics", "sentry", "beacon", "heartbeat", "telemetry", "collect")
NOISE_SEGMENTS = {"log", "logs", "logging"}
IMPORTANT_RESOURCE_TYPES = {"document", "xhr", "fetch"}


@dataclass
class NetworkMonitor:
    page: Any | None = None
    events: list[dict[str, Any]] = field(default_factory=list)

    def attach(self, page: Any) -> None:
        self.page = page
        page.on("request", self.on_request)
        page.on("response", self.on_response)
        page.on("requestfinished", self.on_request_finished)
        page.on("requestfailed", self.on_request_failed)

    def on_request(self, request: Any) -> None:
        self.events.append(base_event("request", request))

    def on_response(self, response: Any) -> None:
        request = response.request
        event = base_event("response", request)
        event["status"] = response.status
        self.events.append(event)

    def on_request_finished(self, request: Any) -> None:
        self.events.append(base_event("requestfinished", request))

    def on_request_failed(self, request: Any) -> None:
        event = base_event("requestfailed", request)
        failure = request.failure
        event["failure"] = failure.get("errorText") if isinstance(failure, dict) else str(failure)
        self.events.append(event)

    def events_for_window(self, start_ts: float, end_ts: float) -> list[dict[str, Any]]:
        return [event for event in self.events if start_ts <= event.get("ts", 0) <= end_ts]


def base_event(event_type: str, request: Any) -> dict[str, Any]:
    return {
        "type": event_type,
        "ts": time.time(),
        "method": request.method,
        "url": request.url,
        "resource_type": request.resource_type,
    }


def is_meaningful_event(event: dict[str, Any]) -> bool:
    resource_type = event.get("resource_type")
    url = (event.get("url") or "").lower()
    if resource_type in STATIC_RESOURCE_TYPES:
        return False
    if any(pattern in url for pattern in NOISE_PATTERNS):
        return False
    parsed = urlparse(url)
    segments = {segment for segment in parsed.path.split("/") if segment}
    if segments & NOISE_SEGMENTS:
        return False
    return resource_type in IMPORTANT_RESOURCE_TYPES


def normalize_url_pattern(method: str, url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or "/"
    parts = ["*" if is_dynamic_segment(part) else part for part in path.split("/") if part]
    suffix = "*" if parsed.query else ""
    normalized_path = "/" + "/".join(parts)
    return f"{method.upper()} **{normalized_path}{suffix}"


def is_dynamic_segment(segment: str) -> bool:
    return bool(re.fullmatch(r"\d+|[0-9a-fA-F-]{8,}|[A-Za-z0-9_-]{16,}", segment))


def infer_wait_after(
    before_url: str,
    after_url: str,
    events: list[dict[str, Any]],
    *,
    timeout: int = 30000,
) -> dict[str, Any]:
    if before_url != after_url:
        return {"kind": "url", "pattern": after_url, "timeout": timeout}
    for event in events:
        if event.get("type") == "response" and event.get("status", 0) in range(200, 400) and is_meaningful_event(event):
            method_pattern = normalize_url_pattern(event.get("method", "GET"), event.get("url", ""))
            method, pattern = method_pattern.split(" ", 1)
            return {
                "kind": "response",
                "method": method,
                "url_pattern": pattern,
                "status": [200, 201, 204, 302],
                "resource_type": event.get("resource_type"),
                "timeout": timeout,
            }
    return {"kind": "none"}
