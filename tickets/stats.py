"""Price maths for the hub, team and arena pages.

The headline price everywhere is SeatGeek's lowest_price ("get-in"). Only
games with a get-in price and at least one listing count. Everything here is
computed from the current build only: there is no comparison with earlier
builds (CLAUDE.md rule 1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import mean, median

from .model import Game, Team


def priced(games: list[Game]) -> list[Game]:
    return [g for g in games if g.price is not None]


def cheapest(games: list[Game], n: int | None = None) -> list[Game]:
    out = sorted(priced(games), key=lambda g: (g.price, g.sort_key))
    return out[:n] if n else out


def most_expensive(games: list[Game], n: int) -> list[Game]:
    return sorted(priced(games), key=lambda g: (-g.price, g.sort_key))[:n]


@dataclass
class TeamStats:
    team: Team
    home: list[Game] = field(default_factory=list)
    road: list[Game] = field(default_factory=list)
    home_avg: float | None = None       # mean get-in over priced games at the home arena
    home_priced: int = 0
    rank: int | None = None              # 1 = most expensive home ticket
    premium: float | None = None         # median road get-in / host average
    premium_games: int = 0
    premium_rank: int | None = None      # 1 = biggest visitor premium

    @property
    def cheapest_home(self) -> Game | None:
        c = cheapest(self.home, 1)
        return c[0] if c else None

    @property
    def cheapest_road(self) -> Game | None:
        c = cheapest(self.road, 1)
        return c[0] if c else None

    @property
    def upcoming(self) -> list[Game]:
        return sorted(self.home + self.road, key=lambda g: g.sort_key)


@dataclass
class Stats:
    teams: dict[str, TeamStats]
    ranking: list[TeamStats]           # by home_avg, most expensive first
    premium: list[TeamStats]           # by premium, biggest first
    week: list[Game]
    week_start: date | None
    week_is_first: bool
    expensive: list[Game]


def compute(games: list[Game], teams: list[Team], today: date, week_days: int, list_size: int) -> Stats:
    ts = {t.code: TeamStats(team=t) for t in teams}
    for g in games:
        ts[g.home.code].home.append(g)
        ts[g.away.code].road.append(g)

    # Home averages use games at the team's own arena only, so an Austin,
    # Paris or Mexico City game doesn't skew the "usual" home price.
    for s in ts.values():
        hp = [g.price for g in priced(s.home) if g.at_home_arena]
        s.home_priced = len(hp)
        s.home_avg = mean(hp) if hp else None

    ranking = sorted((s for s in ts.values() if s.home_avg is not None),
                     key=lambda s: (-s.home_avg, s.team.name))
    for i, s in enumerate(ranking, 1):
        s.rank = i

    # Visitor premium: each road game's get-in over the host's average
    # get-in, median across the visitor's road games. Games away from the
    # host's arena are left out because the host's usual price doesn't apply.
    for s in ts.values():
        ratios = []
        for g in priced(s.road):
            host = ts[g.home.code].home_avg
            if host and g.at_home_arena:
                ratios.append(g.price / host)
        if ratios:
            s.premium = median(ratios)
            s.premium_games = len(ratios)
    prem = sorted((s for s in ts.values() if s.premium is not None),
                  key=lambda s: (-s.premium, s.team.name))
    for i, s in enumerate(prem, 1):
        s.premium_rank = i

    # "This week": the next 7 days. Before the season starts (or in a gap
    # like the All-Star break) there may be nothing in that window, so fall
    # back to the 7 days from the next game, and say so in the heading.
    upcoming = priced([g for g in games if g.date >= today])
    window = [g for g in upcoming if g.date < today + timedelta(days=week_days)]
    week_start, first = today, False
    if not window and upcoming:
        week_start = min(g.date for g in upcoming)
        window = [g for g in upcoming if g.date < week_start + timedelta(days=week_days)]
        first = True
    return Stats(
        teams=ts, ranking=ranking, premium=prem,
        week=cheapest(window, list_size), week_start=week_start if window else None,
        week_is_first=first, expensive=most_expensive(games, list_size),
    )


@dataclass
class VisitorRow:
    team: Team
    games: list[Game]
    get_in: float           # mean get-in of this visitor's games here
    ratio: float            # get_in / host average


def arena_visitors(home_games: list[Game], host_avg: float | None) -> list[VisitorRow]:
    if not host_avg:
        return []
    by_team: dict[str, list[Game]] = {}
    for g in priced(home_games):
        by_team.setdefault(g.away.code, []).append(g)
    rows = []
    for gs in by_team.values():
        avg = mean(g.price for g in gs)
        rows.append(VisitorRow(team=gs[0].away, games=gs, get_in=avg, ratio=avg / host_avg))
    return sorted(rows, key=lambda r: (-r.ratio, r.team.name))


def family_of_four(cheapest_price: float | None, con: dict | None) -> dict | None:
    """4 get-in tickets + parking + 2 beers + 2 sodas + 4 hot dogs, only when
    the arena's concessions entry is filled in."""
    if cheapest_price is None or not con or con.get("status") != "available":
        return None
    need = ("parking", "beer", "soda", "hot_dog")
    if any(not isinstance(con.get(k), (int, float)) for k in need):
        return None
    parts = [
        ("4 get-in tickets", 4 * cheapest_price),
        ("Parking", con["parking"]),
        ("2 beers", 2 * con["beer"]),
        ("2 sodas", 2 * con["soda"]),
        ("4 hot dogs", 4 * con["hot_dog"]),
    ]
    return {"parts": parts, "total": sum(v for _, v in parts)}
