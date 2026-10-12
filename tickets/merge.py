"""Ticketmaster data (from the private nba-tickets-data repo) and the merge
with SeatGeek.

Matching: same local date, same away and home team. When a game moved by a
day between the two feeds (late time-zone edges), a single candidate one
day either side is accepted. Ticketmaster has no home games for CLE, HOU,
MIN, NOP and UTA, so those show SeatGeek only and are not counted as
unmatched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .config import load_json
from .model import Game, TMInfo, Team, game_key, parse_local
from .seatgeek import SGGame


@dataclass
class TMGame:
    key: str
    date: date
    time_local: str | None
    start_utc: str | None
    home: str
    away: str
    venue_name: str
    venue_city: str
    venue_state: str | None
    info: TMInfo


@dataclass
class TMData:
    games: list[TMGame]
    generated: str | None
    checked: str | None
    arena_names: dict[str, str] = field(default_factory=dict)


def load_tm(data_dir: Path) -> TMData:
    schedule = load_json(data_dir / "data/tm/schedule.json")
    try:
        latest = load_json(data_dir / "data/tm/latest.json")
    except OSError:
        latest = {"games": {}}
    status = latest.get("games") or {}
    games = []
    newest_check = None
    for g in schedule.get("games") or []:
        d, t = parse_local(f"{g['local_date']}T{g.get('local_time') or '00:00:00'}")
        if d is None:
            continue
        st = status.get(g["key"], {})
        checked = st.get("checked")
        if checked and (newest_check is None or checked > newest_check):
            newest_check = checked
        venue = g.get("venue") or {}
        games.append(TMGame(
            key=g["key"], date=d, time_local=t if g.get("local_time") else None,
            start_utc=g.get("start_utc"), home=g["home"], away=g["away"],
            venue_name=venue.get("name") or "", venue_city=venue.get("city") or "",
            venue_state=venue.get("state"),
            info=TMInfo(url=g.get("url"), status=st.get("status"), checked=checked,
                        neutral=bool(g.get("neutral_site")), tm_id=g.get("tm_id")),
        ))
    arena_names = {}
    teams_path = data_dir / "config/teams.json"
    if teams_path.exists():
        arena_names = {t["code"]: t.get("arena") for t in load_json(teams_path).get("teams", [])}
    return TMData(games=games, generated=schedule.get("generated"), checked=newest_check,
                  arena_names=arena_names)


@dataclass
class MergeResult:
    games: list[Game]
    matched: int = 0
    sg_only_no_tm_team: int = 0
    sg_unmatched: list[str] = field(default_factory=list)
    tm_unmatched: list[str] = field(default_factory=list)
    shifted: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)


def merge(sg_games: list[SGGame], tm: TMData, teams: list[Team], today: date,
          no_tm_home: set[str]) -> MergeResult:
    by_code = {t.code: t for t in teams}
    tm_upcoming = [g for g in tm.games if g.date >= today and g.home in by_code and g.away in by_code]
    tm_by_key = {g.key: g for g in tm_upcoming}
    used: set[str] = set()
    result = MergeResult(games=[])
    keys_seen: set[str] = set()

    for s in sorted(sg_games, key=lambda x: (x.date, x.time_local or "", x.stats.event_id)):
        key = game_key(s.date, s.away.code, s.home.code)
        if key in keys_seen:
            # SeatGeek lists the occasional game twice (resale and a
            # package); keep the first, which sorts by event id.
            result.duplicates.append(key)
            continue
        keys_seen.add(key)
        tmg = tm_by_key.get(key)
        if tmg is None:
            near = [tm_by_key.get(game_key(s.date + timedelta(days=dd), s.away.code, s.home.code))
                    for dd in (-1, 1)]
            near = [n for n in near if n is not None and n.key not in used]
            if len(near) == 1:
                tmg = near[0]
                result.shifted.append(f"{key} ~ {tmg.key}")
        game = Game(
            key=key, date=s.date, time_local=s.time_local, start_utc=s.start_utc,
            home=s.home, away=s.away, venue_name=s.venue_name, venue_city=s.venue_city,
            venue_state=s.venue_state, sg=s.stats,
        )
        if tmg is not None and tmg.key not in used:
            used.add(tmg.key)
            game.tm = tmg.info
            game.source = "both"
            if not game.start_utc:
                game.start_utc = tmg.start_utc
            result.matched += 1
        else:
            game.source = "seatgeek"
            if s.home.code in no_tm_home:
                result.sg_only_no_tm_team += 1
            else:
                result.sg_unmatched.append(key)
        result.games.append(game)

    for g in tm_upcoming:
        if g.key in used:
            continue
        result.tm_unmatched.append(g.key)
        result.games.append(Game(
            key=g.key, date=g.date, time_local=g.time_local, start_utc=g.start_utc,
            home=by_code[g.home], away=by_code[g.away], venue_name=g.venue_name,
            venue_city=g.venue_city, venue_state=g.venue_state, tm=g.info, source="ticketmaster",
        ))
    result.games.sort(key=lambda g: g.sort_key)
    return result


def expected_upcoming(today: date, build: dict) -> int:
    """Games still to play this season, estimated from the calendar: the
    regular season is spread evenly enough that the share of days left is a
    fair guide. Independent of the Ticketmaster data on purpose, so a broken
    data repo can't lower the SeatGeek floor."""
    start = date.fromisoformat(build["season_start"])
    end = date.fromisoformat(build["season_end"])
    total = int(build.get("games_per_season", 1230))
    if today <= start:
        return total
    if today > end:
        return 0
    return round(total * (end - today).days / (end - start).days)


def required_events(today: date, build: dict) -> int:
    """The SeatGeek floor: min(min_events, min_ratio x games still to play)."""
    return min(int(build["min_events"]),
               int(float(build["min_ratio"]) * expected_upcoming(today, build)))
