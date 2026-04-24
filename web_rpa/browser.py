from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import BrowserLaunchFailed


CHROME_HINT = (
    "无法启动本机 Chrome。请安装 Google Chrome，或在支持的场景中改用 Playwright "
    "Chromium，并确认已运行 `python -m playwright install chromium`。"
)


def ensure_profile_dir(profile: Path | str | None) -> Path:
    path = Path(profile or ".profiles/default")
    path.mkdir(parents=True, exist_ok=True)
    return path


def launch_recording_context(playwright: Any, profile: Path | str, *, browser: str = "chrome"):
    user_data_dir = ensure_profile_dir(profile)
    kwargs: dict[str, Any] = {"user_data_dir": str(user_data_dir), "headless": False}
    if browser == "chrome":
        kwargs["channel"] = "chrome"
    try:
        return playwright.chromium.launch_persistent_context(**kwargs)
    except Exception as exc:  # Playwright raises implementation-specific errors.
        if browser == "chrome":
            raise BrowserLaunchFailed(CHROME_HINT) from exc
        raise BrowserLaunchFailed(f"浏览器启动失败：{exc}") from exc


def launch_replay_browser(playwright: Any, *, headed: bool = False, slow_mo: float = 0):
    try:
        return playwright.chromium.launch(headless=not headed, slow_mo=slow_mo or 0)
    except Exception as exc:
        raise BrowserLaunchFailed(f"回放浏览器启动失败：{exc}") from exc


def maybe_start_trace(context: Any, enabled: bool, *, screenshots: bool = True, snapshots: bool = True) -> None:
    if enabled:
        context.tracing.start(screenshots=screenshots, snapshots=snapshots)


def maybe_stop_trace(context: Any, enabled: bool, path: Path | str) -> str | None:
    if not enabled:
        return None
    trace_path = Path(path)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    context.tracing.stop(path=str(trace_path))
    return str(trace_path)
