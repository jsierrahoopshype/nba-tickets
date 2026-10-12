"""Teams and games.

A Game is one regular-season NBA game, keyed like the Ticketmaster data
repo: <YYYYMMDD>-<AWAY>-<HOME> on the local game date. Its SeatGeek part
(`sg`) lives only in memory for the length of a build and is rendered into
HTML; it is never written anywhere else (CLAUDE.md rule 1).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower().replace(".", "")).strip("-")


@dataclass(frozen=True)
class Team:
    code: str
    name: str
    slug: str
    short_name: str
    short_slug: str
    nba_id: int
    conference: str
    city: str
    state: str | None
    country: str | None
    arena: str
    arena_slug: str
    address: dict
    lat: float
    lon: float
    color: str

    @classmethod
    def from_dict(cls, d: dict) -> "Team":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})


def load_teams(teams_raw: dict) -> list[Team]:
    teams = [Team.from_dict(t) for t in teams_raw["teams"]]
    if len(teams) != 30:
        raise ValueError(f"config/teams.json has {len(teams)} teams, expected 30")
    for attr in ("code", "slug", "short_slug", "arena_slug"):
        values = [getattr(t, attr) for t in teams]
        if len(set(values)) != len(values):
            raise ValueError(f"config/teams.json: duplicate {attr}")
    return sorted(teams, key=lambda t: t.name)


@dataclass
class SGStats:
    """SeatGeek's per-event fields. In memory only."""
    event_id: int
    url: str
    lowest: float | None
    median: float | None
    average: float | None
    highest: float | None
    listings: int | None

    @property
    def priced(self) -> bool:
        """A positive lowest_price is a price. listing_count is extra
        information shown beside it when SeatGeek sends it; a missing count
        never hides a price."""
        return self.lowest is not None and self.lowest > 0

    @property
    def no_listings(self) -> bool:
        """SeatGeek said so explicitly: listing_count is 0. A missing or empty
        stats object is not the same thing, it means no price data at all."""
        return not self.priced and self.listings == 0


@dataclass
class TMInfo:
    url: str | None
    status: str | None
    checked: str | None
    neutral: bool = False
    tm_id: str | None = None


@dataclass
class Game:
    key: str
    date: date
    time_local: str | None          # "19:30", None when TBD
    start_utc: str | None           # ISO 8601 with Z, for JSON-LD
    home: Team
    away: Team
    venue_name: str
    venue_city: str
    venue_state: str | None
    sg: SGStats | None = None
    tm: TMInfo | None = None
    source: str = ""                # "both", "seatgeek", "ticketmaster"
    flags: set = field(default_factory=set)

    @property
    def at_home_arena(self) -> bool:
        if self.tm and self.tm.neutral:
            return False
        if norm_venue(self.venue_name) == norm_venue(self.home.arena):
            return True
        # Ticketmaster and SeatGeek sometimes spell an arena differently; the
        # home city is a safe second check except for alternate venues
        # (Spurs in Austin), which have a different city anyway.
        return norm_city(self.venue_city) == norm_city(self.home.city)

    @property
    def price(self) -> float | None:
        return self.sg.lowest if self.sg and self.sg.priced else None

    @property
    def sort_key(self):
        return (self.date, self.time_local or "99:99", self.key)

    @property
    def anchor(self) -> str:
        return f"g-{self.key}"

    @property
    def matchup_slug(self) -> str:
        return matchup_slug(self.away, self.home)


def matchup_slug(away: Team, home: Team) -> str:
    return f"{away.short_slug}-at-{home.short_slug}"


def game_key(d: date, away: str, home: str) -> str:
    return f"{d:%Y%m%d}-{away}-{home}"


def norm_venue(name: str | None) -> str:
    n = slugify(name or "")
    for suffix in ("-atx",):
        if n.endswith(suffix):
            n = n[: -len(suffix)]
    return n


def norm_city(name: str | None) -> str:
    return slugify(name or "").replace("saint-", "st-")


def parse_local(dt: str | None) -> tuple[date | None, str | None]:
    """'2026-10-21T19:30:00' -> (date, '19:30')."""
    if not dt:
        return None, None
    try:
        parsed = datetime.fromisoformat(dt.replace("Z", ""))
    except ValueError:
        return None, None
    return parsed.date(), parsed.strftime("%H:%M")
