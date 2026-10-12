"""Build the whole section into an output directory.

Order matters for the SeatGeek rules (CLAUDE.md): the API response is
parsed in memory, checked against the event floor, merged with the
Ticketmaster data and rendered. Only HTML (plus sitemap.xml, CSS, JS, fonts
and logos) is written to the output directory. The hash state and the build
report written to main hold no SeatGeek numbers.
"""

from __future__ import annotations

import shutil
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from statistics import mean

from . import config, lastmod
from .links import Links
from .merge import MergeResult, TMData, merge, required_events
from .model import Game, Team, load_teams
from .render import Renderer, file_hash, sports_event
from .seatgeek import ParseResult, parse_events
from .stats import arena_visitors, cheapest, compute, family_of_four, priced

ASSETS = config.ROOT / "assets"
EXPECTED_PAGES = 1 + 30 + 30 + 870 + 1 + 1


class BuildError(RuntimeError):
    pass


@dataclass
class BuildResult:
    parsed: ParseResult
    merged: MergeResult
    required: int
    pages: dict = field(default_factory=dict)          # type -> count
    noindex: int = 0
    sitemap_urls: int = 0
    changed: int = 0
    logos: int = 0
    arena_mismatch: list = field(default_factory=list)
    tm_generated: str | None = None
    tm_checked: str | None = None


def fetch_logos(teams: list[Team], url_template: str, dest: Path) -> dict[str, str]:
    """Team logos from jsierrahoopshype/nba-headshots, copied into the site so
    the reader's browser asks no other domain for anything."""
    dest.mkdir(parents=True, exist_ok=True)
    found = {}
    for t in teams:
        try:
            with urllib.request.urlopen(url_template.format(nba_id=t.nba_id), timeout=20) as r:
                body = r.read()
        except Exception:
            continue
        if b"<svg" not in body[:2000]:
            continue
        (dest / f"{t.code.lower()}.svg").write_bytes(body)
        found[t.code] = config.site_path(f"assets/logos/{t.code.lower()}.svg")
    return found


def build(out: Path, settings: config.Settings, sg_raw: list[dict], tm: TMData, today: date,
          now: datetime, state_path: Path, logos: bool = True,
          min_events: int | None = None) -> BuildResult:
    b = settings.build
    teams = load_teams(settings.teams_raw)
    by_code = {t.code: t for t in teams}
    no_tm_home = set(b.get("no_tm_home_teams") or [])

    parsed = parse_events(sg_raw, teams, b)
    required = required_events(today, b) if min_events is None else min_events
    if len(parsed.games) < required:
        raise BuildError(
            f"SeatGeek returned {len(parsed.games)} NBA regular-season games "
            f"({parsed.raw_count} events), fewer than the floor of {required}. Nothing was published."
        )
    merged = merge(parsed.games, tm, teams, today, no_tm_home)
    games = [g for g in merged.games if g.date >= today]
    st = compute(games, teams, today, int(b.get("week_days", 7)), int(b.get("list_size", 10)))
    result = BuildResult(parsed=parsed, merged=merged, required=required,
                         tm_generated=tm.generated, tm_checked=tm.checked)
    result.arena_mismatch = [
        f"{c}: config says {by_code[c].arena!r}, data repo says {a!r}"
        for c, a in sorted(tm.arena_names.items()) if c in by_code and a and a != by_code[c].arena
    ]

    # ---- output tree: assets first
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copytree(ASSETS, out / "assets")
    (out / ".nojekyll").write_text("")
    logo_paths = fetch_logos(teams, b["logos_url"], out / "assets/logos") if logos else {}
    result.logos = len(logo_paths)
    sg_logo = next((config.site_path(f"assets/brand/{p.name}") for p in sorted((ASSETS / "brand").glob("seatgeek-logo.*"))), None) \
        if (ASSETS / "brand").exists() else None
    asset_hashes = {str(p.relative_to(config.ROOT)): file_hash(p)
                    for p in ASSETS.rglob("*") if p.is_file() and p.suffix in (".css", ".js")}

    links = Links(settings.affiliate)
    r = Renderer(settings, links, logo_paths, now, no_tm_home, sg_logo, asset_hashes,
                 prices_available=bool(priced(games)))
    copy = settings.copy
    season = copy["season_label"]
    launched = settings.launched
    hub_crumb = (copy["tabs"]["hub"], config.site_path())
    con = settings.concessions.get("teams", {})

    pages: dict[str, tuple[str, str, bool]] = {}   # rel -> (html, type, indexable)

    def emit(kind: str, rel: str, html: str, indexable: bool) -> None:
        pages[rel] = (html, kind, indexable)

    # ---- hub
    my_team = {}
    for t in teams:
        ts = st.teams[t.code]
        up = ts.upcoming
        c = cheapest(up, 1)
        my_team[t.code] = {"cheapest": c[0] if c else None, "next": up[:3]}
    page = r.page("", copy["hub"]["title"].format(season=season),
                  copy["hub"]["description"].format(season=season),
                  copy["hub"]["h1"].format(season=season), [], noindex=not launched, tab="hub")
    emit("hub", "", r.render("hub.html", page=page, st=st, teams=teams, my_team=my_team,
                              arenas=sorted(teams, key=lambda t: t.arena)), True)

    # ---- team pages
    ranked_n = len(st.ranking)
    prem_n = len(st.premium)
    for t in teams:
        ts = st.teams[t.code]
        kw = dict(season=season, team=t.short_name, full_team=t.name, arena=t.arena, city=t.city)
        page = r.page(f"{t.slug}/", copy["team"]["title"].format(**kw), copy["team"]["description"].format(**kw),
                      copy["team"]["h1"].format(**kw), [hub_crumb, (t.short_name, "")], noindex=not launched,
                      tab="teams")
        emit("team", f"{t.slug}/", r.render("team.html", page=page, t=t, ts=ts, kw=kw, ranked_n=ranked_n,
                                            prem_n=prem_n, con=con.get(t.code), no_tm=t.code in no_tm_home), True)

    # ---- arena pages
    for t in teams:
        ts = st.teams[t.code]
        here = [g for g in ts.home if g.at_home_arena]
        hp = [g.price for g in priced(here)]
        avg = mean(hp) if hp else None
        kw = dict(season=season, team=t.short_name, full_team=t.name, arena=t.arena, city=t.city,
                  avg=f"${avg:,.0f}" if avg else "n/a")
        cheapest_nights = cheapest(here, 5)
        fam = family_of_four(cheapest_nights[0].price if cheapest_nights else None, con.get(t.code))
        page = r.page(f"arenas/{t.arena_slug}/", copy["arena"]["title"].format(**kw),
                      copy["arena"]["description"].format(**kw), copy["arena"]["h1"].format(**kw),
                      [hub_crumb, (copy["tabs"]["arenas"], config.site_path() + "#arenas"), (t.arena, "")],
                      noindex=not launched, tab="arenas")
        emit("arena", f"arenas/{t.arena_slug}/", r.render(
            "arena.html", page=page, t=t, kw=kw, games=here, avg=avg, cheapest_nights=cheapest_nights,
            visitors=arena_visitors(here, avg), con=con.get(t.code), family=fam), True)

    # ---- matchup pages: every away-at-home pairing
    pair_games: dict[tuple[str, str], list[Game]] = {}
    for g in games:
        pair_games.setdefault((g.away.code, g.home.code), []).append(g)
    for away in teams:
        for home in teams:
            if away is home:
                continue
            gs = pair_games.get((away.code, home.code), [])
            rel = f"{away.short_slug}-at-{home.short_slug}/"
            kw = dict(season=season, away=away.short_name, home=home.short_name, away_full=away.name,
                      home_full=home.name, arena=home.arena)
            canonical = config.public_url(rel)
            jsonld = {"@context": "https://schema.org", "@graph": [sports_event(g, canonical) for g in gs]} if gs else None
            # A pairing with nothing left to play is kept for readers but kept
            # out of Google: noindex and out of the sitemap.
            indexable = bool(gs)
            page = r.page(rel, copy["matchup"]["title"].format(**kw), copy["matchup"]["description"].format(**kw),
                          copy["matchup"]["h1"].format(**kw),
                          [hub_crumb, (home.short_name, config.site_path(home.slug + "/")),
                           (f"{away.short_name} at {home.short_name}", "")],
                          noindex=(not launched) or not indexable, tab="teams", jsonld=jsonld)
            emit("matchup", rel, r.render("matchup.html", page=page, away=away, home=home, games=gs, kw=kw), indexable)

    # ---- road trip tool: its game data is embedded in the page (rule 1)
    rt_games = [
        [g.date.isoformat(), g.time_local or "", g.home.code, g.away.code, round(g.price),
         round(g.sg.median) if g.sg.median else None, g.sg.listings, links.wrap("seatgeek", g.sg.url)[0],
         links.wrap("ticketmaster", g.tm.url)[0] if g.tm and g.tm.url else "", g.matchup_slug]
        for g in priced(games)
    ]
    rt_data = {
        "games": rt_games,
        "teams": {t.code: [t.short_name, t.city, t.slug, t.arena] for t in teams},
        "miles": settings.distances["miles"],
        "drivable": settings.distances["drivable_miles"],
        "maxHop": settings.distances["max_hop_miles"],
        "first": games[0].date.isoformat() if games else today.isoformat(),
        "last": games[-1].date.isoformat() if games else today.isoformat(),
        "base": config.site_path(),
        "sponsored": links.enabled("seatgeek"),
    }
    page = r.page("road-trip/", copy["road_trip"]["title"].format(season=season),
                  copy["road_trip"]["description"].format(season=season), copy["road_trip"]["h1"],
                  [hub_crumb, (copy["tabs"]["road_trip"], "")], noindex=not launched, tab="road_trip")
    emit("road_trip", "road-trip/", r.render("road_trip.html", page=page, rt_data=rt_data, teams=teams), True)

    # ---- terms
    page = r.page("terms/", copy["terms"]["title"], copy["terms"]["description"], copy["terms"]["h1"],
                  [hub_crumb, (copy["terms"]["h1"], "")], noindex=not launched, has_prices=False)
    emit("terms", "terms/", r.render("terms.html", page=page), True)

    if len(pages) != EXPECTED_PAGES:
        raise BuildError(f"rendered {len(pages)} pages, expected {EXPECTED_PAGES}")

    for rel, (html, kind, _) in pages.items():
        target = out / rel / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")
        result.pages[kind] = result.pages.get(kind, 0) + 1

    # ---- lastmod + sitemap
    prev = lastmod.read_state(state_path)
    state, result.changed = lastmod.update(
        prev, {config.public_url(rel): html for rel, (html, _, _) in pages.items()}, today.isoformat())
    lastmod.write_state(state_path, state)
    urls = [] if not launched else [
        (config.public_url(rel), state[config.public_url(rel)][1])
        for rel, (_, _, indexable) in sorted(pages.items()) if indexable
    ]
    result.sitemap_urls = len(urls)
    result.noindex = sum(1 for _, _, ix in pages.values() if not launched or not ix)
    body = "".join(f"  <url><loc>{u}</loc><lastmod>{d}</lastmod></url>\n" for u, d in urls)
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + body + "</urlset>\n",
        encoding="utf-8")
    return result
