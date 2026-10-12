"""python -m tickets build [--offline] --out site

Live (GitHub Actions): SeatGeek from the API (SEATGEEK_CLIENT_ID), the
Ticketmaster data from a checkout of nba-tickets-data (--data-dir).
Offline: both from fixtures/, no network except the team logos
(--no-logos skips those too).
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from . import config, report
from .build import BuildError, build
from .merge import load_tm
from .seatgeek import SeatGeekError, fetch_events, load_fixture


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tickets")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build the site")
    b.add_argument("--out", type=Path, default=Path("site"))
    b.add_argument("--offline", action="store_true", help="use fixtures/ instead of the APIs")
    b.add_argument("--fixtures", type=Path, default=config.ROOT / "fixtures")
    b.add_argument("--data-dir", type=Path, help="checkout of nba-tickets-data (live builds)")
    b.add_argument("--today", help="YYYY-MM-DD, default: today in UTC")
    b.add_argument("--now", help="ISO time for the 'updated' stamp, default: now in UTC")
    b.add_argument("--no-logos", action="store_true")
    b.add_argument("--state", type=Path, help="page hash file (default state/page-hashes.json live, .offline/ offline)")
    b.add_argument("--report", type=Path, help="report file (default reports/last-build.md live, .offline/ offline)")
    b.add_argument("--min-events", type=int, help="override the SeatGeek floor (offline default 0)")
    args = ap.parse_args(argv)

    now = datetime.fromisoformat(args.now).astimezone(timezone.utc) if args.now else datetime.now(timezone.utc)
    today = date.fromisoformat(args.today) if args.today else now.date()
    settings = config.load_settings()
    scratch = config.ROOT / ".offline"
    state = args.state or (scratch / "page-hashes.json" if args.offline else config.ROOT / "state/page-hashes.json")
    report_path = args.report or (scratch / "last-build.md" if args.offline else config.ROOT / "reports/last-build.md")

    try:
        if args.offline:
            sg_raw = load_fixture(args.fixtures / "seatgeek")
            tm = load_tm(args.fixtures / "data-repo")
            min_events = 0 if args.min_events is None else args.min_events
        else:
            if not args.data_dir:
                print("build: --data-dir (checkout of nba-tickets-data) is required for a live build", file=sys.stderr)
                return 2
            sg_raw = fetch_events(os.environ.get("SEATGEEK_CLIENT_ID", "").strip(), today, settings.build)
            tm = load_tm(args.data_dir)
            min_events = args.min_events
        res = build(args.out, settings, sg_raw, tm, today, now, state, logos=not args.no_logos,
                    min_events=min_events)
        del sg_raw  # nothing from the SeatGeek response outlives the render
    except (SeatGeekError, BuildError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    report.write(report_path, res, now, "offline fixtures" if args.offline else "live",
                 os.environ.get("GITHUB_SHA"))
    print(f"build: {sum(res.pages.values())} pages, {len(res.parsed.games)} SeatGeek games, "
          f"{res.merged.matched} matched with Ticketmaster, {res.changed} changed, "
          f"{res.sitemap_urls} in sitemap -> {args.out}")
    return 0
