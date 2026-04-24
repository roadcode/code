from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .errors import WebRpaError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m web_rpa")
    subparsers = parser.add_subparsers(dest="command", required=True)

    record = subparsers.add_parser("record", help="record a browser flow")
    record.add_argument("--url", required=True, help="initial URL to record")
    record.add_argument("--out", required=True, type=Path, help="flow JSON output path")
    record.add_argument("--profile", type=Path, default=Path(".profiles/default"))
    record.add_argument("--browser", choices=["chrome", "chromium"], default="chrome")
    record.add_argument("--name", help="flow name; defaults to output file stem")

    run = subparsers.add_parser("run", help="run a recorded flow")
    run.add_argument("--flow", required=True, type=Path, help="flow JSON path")
    run.add_argument("--vars", type=Path, help="JSON variables file")
    run.add_argument("--profile", type=Path, help="optional persistent profile directory")
    run.add_argument("--headed", action="store_true", help="run with a visible browser")
    run.add_argument("--slow-mo", type=float, default=0, help="slow motion delay in ms")
    run.add_argument("--trace", action="store_true", help="save Playwright trace")
    run.add_argument("--report-out", type=Path, default=Path("runs/report.json"))

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "record":
            from .recorder import record_flow

            record_flow(args)
            return 0
        if args.command == "run":
            from .replay import run_flow

            return 0 if run_flow(args).status == "passed" else 1
    except WebRpaError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 2
    return 1
