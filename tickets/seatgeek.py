"""SeatGeek Platform API: fetch NBA events at build time, in memory only.

CLAUDE.md rule 1: nothing in this module writes to disk. The raw response is
parsed into SGStats on Game objects and dropped; the numbers reach the
outside world only inside rendered HTML. Do not add caching, dumps or debug
files here. Errors never echo the client id.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .model import Team, SGStats, parse_local, slugify

API_URL = "https://api.seatgeek.com/2/events"


class SeatGeekError(RuntimeError):
    pass


def fetch_events(client_id: str, today: date, build: dict, session=None) -> list[dict]:
    """Every NBA event from today on, paged. Returns the raw event dicts."""
    import requests

    if not client_id:
        raise SeatGeekError("SEATGEEK_CLIENT_ID is not set")
    http = session or requests.Session()
    per_page = int(build.get("seatgeek_per_page", 100))
    max_pages = int(build.get("seatgeek_max_pages", 30))
    events: list[dict] = []
    page, total = 1, None
    while page <= max_pages:
        params = {
            "client_id": client_id,
            "taxonomies.name": "nba",
            "per_page": per_page,
            "page": page,
            "sort": "datetime_utc.asc",
            "datetime_utc.gte": today.isoformat(),
            "datetime_utc.lte": build["season_end"],
        }
        data = _get(http, API_URL, params, client_id)
        batch = data.get("events") or []
        events.extend(batch)
        total = (data.get("meta") or {}).get("total", total)
        if not batch or (total is not None and page * per_page >= total):
            break
        page += 1
    return events


def _get(http, url: str, params: dict, client_id: str) -> dict:
    delay = 2.0
    for attempt in range(4):
        try:
            resp = http.get(url, params=params, timeout=30)
        except Exception as exc:  # network error: retry, never print params
            err = f"network error ({type(exc).__name__})"
        else:
            if resp.status_code == 200:
                return resp.json()
            err = f"HTTP {resp.status_code}"
            if resp.status_code in (401, 403):
                raise SeatGeekError(f"SeatGeek refused the client id ({err})")
            if resp.status_code not in (429,) and resp.status_code < 500:
                raise SeatGeekError(f"SeatGeek {err}: {resp.text[:200].replace(client_id, '***')}")
        if attempt < 3:
            time.sleep(delay)
            delay *= 2
    raise SeatGeekError(f"SeatGeek failed after retries: {err}")


def fetch_event_stats(client_id: str, event_id: int, session=None) -> dict | None:
    """The single-event endpoint's stats for one event (one call, used only by
    the stats check in the build report). Returns None on any error."""
    import requests

    http = session or requests.Session()
    try:
        data = _get(http, f"{API_URL}/{int(event_id)}", {"client_id": client_id}, client_id)
    except SeatGeekError:
        return None
    return data.get("stats") if isinstance(data, dict) else None


STAT_KEYS = ("lowest_price", "median_price", "average_price", "highest_price",
             "listing_count", "visible_listing_count")


def diagnose(raw: list[dict], build: dict) -> dict:
    """What the response actually carries in `stats`, for the build report:
    how many events have each stats field filled, plus one regular-season
    event's top-level field names and its full stats object. Counts only,
    apart from that one sample."""
    start = date.fromisoformat(build["season_start"])
    counts = {"events": len(raw), "with_stats_object": 0, "lowest_price_present": 0,
              "lowest_price_positive": 0, "listing_count_positive": 0,
              "visible_listing_count_positive": 0}
    filled: dict[str, int] = {}
    sample = None
    for ev in raw:
        stats = ev.get("stats")
        if isinstance(stats, dict):
            counts["with_stats_object"] += 1
            for k, v in stats.items():
                if v is not None:
                    filled[k] = filled.get(k, 0) + 1
        else:
            stats = {}
        low = _num(stats.get("lowest_price"))
        counts["lowest_price_present"] += low is not None
        counts["lowest_price_positive"] += bool(low and low > 0)
        counts["listing_count_positive"] += bool((_num(stats.get("listing_count")) or 0) > 0)
        counts["visible_listing_count_positive"] += bool((_num(stats.get("visible_listing_count")) or 0) > 0)
        d, _ = parse_local(ev.get("datetime_local"))
        if sample is None and d is not None and d >= start and len(ev.get("performers") or []) >= 2:
            sample = ev
    return {
        "counts": counts,
        "filled": dict(sorted(filled.items())),
        "sample_id": sample.get("id") if sample else None,
        "sample_fields": sorted(sample.keys()) if sample else [],
        "sample_stats": sample.get("stats") if sample else None,
        "single_event_stats": None,
    }


def load_fixture(directory: Path) -> list[dict]:
    """The synthetic offline response: fixtures/seatgeek/page-*.json."""
    events: list[dict] = []
    for path in sorted(directory.glob("page-*.json")):
        events.extend(json.loads(path.read_text(encoding="utf-8")).get("events") or [])
    return events


# ---------------------------------------------------------------- parsing

@dataclass
class SGGame:
    """One SeatGeek event that is a regular-season game between two NBA teams."""
    date: date
    time_local: str | None
    start_utc: str | None
    home: Team
    away: Team
    venue_name: str
    venue_city: str
    venue_state: str | None
    stats: SGStats
    home_from: str   # "flag", "title" or "venue"


@dataclass
class ParseResult:
    games: list[SGGame] = field(default_factory=list)
    raw_count: int = 0
    skipped: dict = field(default_factory=dict)

    def skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1


class TeamMatcher:
    """Finds the NBA team behind a SeatGeek performer: by slug, full name or
    nickname ("Trail Blazers"), so a renamed slug (la-clippers vs.
    los-angeles-clippers) still matches."""

    def __init__(self, teams: list[Team]):
        self.by_key: dict[str, Team] = {}
        for t in teams:
            for k in (t.slug, slugify(t.name), slugify(f"{t.city} {t.short_name}")):
                self.by_key[k] = t
        self.by_key["los-angeles-clippers"] = next(t for t in teams if t.code == "LAC")
        self.nicknames = sorted(((slugify(t.short_name), t) for t in teams), key=lambda x: -len(x[0]))

    def match(self, performer: dict) -> Team | None:
        for k in (performer.get("slug"), slugify(performer.get("name") or "")):
            if k and k in self.by_key:
                return self.by_key[k]
        name = "-" + slugify(performer.get("name") or "") + "-"
        for nick, team in self.nicknames:
            if f"-{nick}-" in name:
                return team
        return None


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _count(stats: dict) -> int | None:
    for key in ("listing_count", "visible_listing_count"):
        v = _num(stats.get(key))
        if v is not None:
            return int(v)
    return None


def parse_events(raw: list[dict], teams: list[Team], build: dict) -> ParseResult:
    matcher = TeamMatcher(teams)
    start = date.fromisoformat(build["season_start"])
    end = date.fromisoformat(build["season_end"])
    out = ParseResult(raw_count=len(raw))
    seen: set[int] = set()
    for ev in raw:
        eid = ev.get("id")
        if eid in seen:
            out.skip("duplicate event id")
            continue
        seen.add(eid)
        d, t = parse_local(ev.get("datetime_local"))
        if d is None:
            out.skip("no date")
            continue
        if d < start or d > end:
            out.skip("outside the regular season")
            continue
        found = [(p, matcher.match(p)) for p in ev.get("performers") or []]
        nba = [(p, tm) for p, tm in found if tm is not None]
        if len({tm.code for _, tm in nba}) != 2:
            out.skip("not two NBA teams")
            continue
        home = away = None
        home_from = "flag"
        for p, tm in nba:
            if p.get("home_team"):
                home = tm
            elif p.get("away_team"):
                away = tm
        pair = [tm for _, tm in nba]
        if home and not away:
            away = next(x for x in pair if x is not home)
        elif away and not home:
            home = next(x for x in pair if x is not away)
        venue = ev.get("venue") or {}
        if not home:
            home, away, home_from = _guess_home(ev, pair, venue)
        if not home or home is away:
            out.skip("home team unknown")
            continue
        stats = ev.get("stats") or {}
        tbd = bool(ev.get("time_tbd") or ev.get("datetime_tbd"))
        utc = ev.get("datetime_utc")
        out.games.append(SGGame(
            date=d,
            time_local=None if tbd else t,
            start_utc=None if tbd or not utc else (utc if utc.endswith("Z") else utc + "Z"),
            home=home, away=away,
            venue_name=venue.get("name") or "",
            venue_city=venue.get("city") or "",
            venue_state=venue.get("state"),
            stats=SGStats(
                event_id=eid,
                url=ev.get("url") or "",
                lowest=_num(stats.get("lowest_price")),
                median=_num(stats.get("median_price")),
                average=_num(stats.get("average_price")),
                highest=_num(stats.get("highest_price")),
                listings=_count(stats),
            ),
            home_from=home_from,
        ))
    return out


def _guess_home(ev: dict, pair: list[Team], venue: dict):
    """No home_team flag: 'Away at Home' in the title, then the venue city."""
    title = slugify(ev.get("title") or "")
    if "-at-" in title:
        left, right = title.split("-at-", 1)
        for i, t in enumerate(pair):
            if slugify(t.short_name) in right and slugify(pair[1 - i].short_name) in left:
                return t, pair[1 - i], "title"
    city = slugify(venue.get("city") or "")
    for i, t in enumerate(pair):
        if slugify(t.city) == city:
            return t, pair[1 - i], "venue"
    return None, None, ""
