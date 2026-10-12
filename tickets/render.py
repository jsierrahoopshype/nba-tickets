"""Jinja2 environment, filters and page metadata."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markupsafe import Markup

from . import config
from .model import Game

TEMPLATES = config.ROOT / "templates"


def money(v) -> str:
    if v is None:
        return ""
    return f"${v:,.0f}"


def ratio(v) -> str:
    return "" if v is None else f"{v:.2f}x"


def pct_diff(v) -> str:
    """1.24 -> '+24%', 0.9 -> '-10%'."""
    if v is None:
        return ""
    p = round((v - 1) * 100)
    return f"+{p}%" if p > 0 else (f"{p}%" if p < 0 else "even")


def dshort(d: date) -> str:
    return f"{d:%a}, {d:%b} {d.day}"


def dlong(d: date) -> str:
    return f"{d:%A}, {d:%B} {d.day}, {d.year}"


def time12(t: str | None) -> str:
    if not t:
        return "Time TBD"
    h, m = (int(x) for x in t.split(":")[:2])
    return f"{(h % 12) or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def cut(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def fmt(template: str, **kw) -> str:
    return template.format(**kw)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:10]


class Renderer:
    def __init__(self, settings, links, logos: dict[str, str], updated: datetime,
                 no_tm_home: set[str], seatgeek_logo: str | None, asset_hashes: dict[str, str],
                 prices_available: bool = True):
        self.settings = settings
        self.copy = settings.copy
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATES)),
            autoescape=select_autoescape(["html", "xml"]),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.filters.update(money=money, ratio=ratio, pct_diff=pct_diff, dshort=dshort,
                                dlong=dlong, time12=time12)
        self.env.globals.update(
            site_path=config.site_path,
            public_url=config.public_url,
            copy=self.copy,
            fmt=fmt,
            links=links,
            any_affiliate=links.any_enabled,
            logo=lambda team: logos.get(team.code),
            asset=lambda rel: config.site_path(rel) + (f"?v={asset_hashes[rel]}" if rel in asset_hashes else ""),
            how_to_watch=lambda team: self.copy["how_to_watch_url"].format(slug=team.slug),
            team_path=lambda team: config.site_path(team.slug + "/"),
            arena_path=lambda team: config.site_path(f"arenas/{team.arena_slug}/"),
            matchup_path=lambda away, home: config.site_path(f"{away.short_slug}-at-{home.short_slug}/"),
            game_path=lambda g: config.site_path(f"{g.matchup_slug}/") + f"#{g.anchor}",
            status_of=self.status_of,
            updated_iso=updated.strftime("%Y-%m-%dT%H:%MZ"),
            updated_label=f"{updated:%b} {updated.day}, {updated:%Y}, {updated:%H:%M} UTC",
            seatgeek_home=config.SEATGEEK_HOME,
            seatgeek_logo=seatgeek_logo,
            no_tm_home=no_tm_home,
            terms_path=config.site_path("terms/"),
            # False when SeatGeek sent no prices at all this build: empty
            # sections then say prices are unavailable, not "no listings".
            prices_available=prices_available,
        )
        self.no_tm_home = no_tm_home

    def status_of(self, g: Game) -> tuple[str, str]:
        """(css class, label) for a game's status chip."""
        st = self.copy["status"]
        if g.tm and g.tm.status:
            s = g.tm.status.lower()
            if "sold" in s:
                return "bad", st["soldout"]
            if s in st:
                return ("ok" if s == "onsale" else "bad"), st[s]
            return "muted", s.title()
        if g.home.code in self.no_tm_home:
            return "muted", st["no_tm"]
        return "", ""

    def page(self, rel: str, title: str, description: str, h1: str, crumbs: list,
             noindex: bool, tab: str = "", jsonld=None, has_prices: bool = True) -> dict:
        return {
            "rel": rel,
            "title": cut(title, 60),
            "description": cut(description, 155),
            "canonical": config.public_url(rel),
            "h1": h1,
            "crumbs": crumbs,
            "noindex": noindex,
            "tab": tab,
            "jsonld": Markup(json.dumps(jsonld, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")) if jsonld else None,
            "has_prices": has_prices,
        }

    def render(self, template: str, **ctx) -> str:
        return self.env.get_template(template).render(**ctx)


def sports_event(g: Game, canonical: str) -> dict:
    """schema.org SportsEvent without offers or prices."""
    status = {
        "cancelled": "https://schema.org/EventCancelled",
        "postponed": "https://schema.org/EventPostponed",
        "rescheduled": "https://schema.org/EventRescheduled",
    }.get((g.tm.status or "").lower() if g.tm else "", "https://schema.org/EventScheduled")
    if g.at_home_arena and g.home.address:
        location = {"@type": "Place", "name": g.home.arena,
                    "address": {"@type": "PostalAddress", **g.home.address}}
    else:
        location = {"@type": "Place", "name": g.venue_name or g.home.arena,
                    "address": {"@type": "PostalAddress", "addressLocality": g.venue_city or g.home.city}}
    ev = {
        "@type": "SportsEvent",
        "name": f"{g.away.name} at {g.home.name}",
        "sport": "Basketball",
        "url": f"{canonical}#{g.anchor}",
        "eventStatus": status,
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "location": location,
        "homeTeam": {"@type": "SportsTeam", "name": g.home.name},
        "awayTeam": {"@type": "SportsTeam", "name": g.away.name},
        "competitor": [{"@type": "SportsTeam", "name": g.home.name},
                       {"@type": "SportsTeam", "name": g.away.name}],
    }
    ev["startDate"] = g.start_utc or g.date.isoformat()
    return ev
