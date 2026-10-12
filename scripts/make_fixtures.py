#!/usr/bin/env python3
"""Regenerate the synthetic offline fixtures under fixtures/.

Everything here is made up (seeded random): no real SeatGeek or
Ticketmaster response is recorded or stored in this repo (CLAUDE.md rule 1).
The shapes follow the SeatGeek Platform API events response and the
nba-tickets-data schedule.json / latest.json layout, with the edge cases the
build must handle:

- a preseason game and a parking event (both skipped),
- a game listed twice on SeatGeek (duplicate dropped),
- a game with no home_team flags (home from the title),
- a game with no listings (shown unpriced),
- the Clippers under SeatGeek's older slug los-angeles-clippers,
- CLE/HOU/MIN/NOP/UTA home games with no Ticketmaster entry,
- one SeatGeek game missing from Ticketmaster, one Ticketmaster-only game,
  one game a day apart between the two, one off-sale game.
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "fixtures"
NO_TM = {"CLE", "HOU", "MIN", "NOP", "UTA"}
TZ_OFFSET = {  # hours behind UTC in late October (DST), close enough for fixtures
    "ATL": 4, "BOS": 4, "BKN": 4, "CHA": 4, "CHI": 5, "CLE": 4, "DAL": 5, "DEN": 6, "DET": 4,
    "GSW": 7, "HOU": 5, "IND": 4, "LAC": 7, "LAL": 7, "MEM": 5, "MIA": 4, "MIL": 5, "MIN": 5,
    "NOP": 5, "NYK": 4, "OKC": 5, "ORL": 4, "PHI": 4, "PHX": 7, "POR": 7, "SAC": 7, "SAS": 5,
    "TOR": 4, "UTA": 6, "WAS": 4,
}


def main() -> None:
    rng = random.Random(2627)
    teams = json.loads((ROOT / "config/teams.json").read_text())["teams"]
    by = {t["code"]: t for t in teams}
    codes = sorted(by)
    base = {c: rng.randint(18, 95) for c in codes}
    star = {c: rng.uniform(0.8, 1.6) for c in codes}

    # 15 game days, 6-8 games a day, no team twice on one day.
    games = []
    start = date(2026, 10, 20)
    for day in range(15):
        d = start + timedelta(days=day)
        pool = codes[:]
        rng.shuffle(pool)
        for i in range(rng.randint(6, 8)):
            home, away = pool[2 * i], pool[2 * i + 1]
            games.append((d, rng.choice(["19:00", "19:30", "20:00", "22:00"]), home, away))

    sg_events, tm_games, latest = [], [], {}
    eid = 7_100_000
    for n, (d, t, home, away) in enumerate(games):
        eid += 1
        h, a = by[home], by[away]
        local = datetime.fromisoformat(f"{d}T{t}:00")
        utc = local + timedelta(hours=TZ_OFFSET[home])
        low = max(6, round(base[home] * star[away] * rng.uniform(0.75, 1.3)))
        listings = rng.randint(40, 900)
        stats = {
            "listing_count": listings, "visible_listing_count": listings,
            "lowest_price": low, "median_price": round(low * rng.uniform(1.6, 2.4)),
            "average_price": round(low * rng.uniform(2.0, 3.0)),
            "highest_price": round(low * rng.uniform(15, 40)),
        }
        if n == 11:  # no listings yet
            stats = {"listing_count": 0, "visible_listing_count": 0, "lowest_price": None,
                     "median_price": None, "average_price": None, "highest_price": None}
        hp = performer(h, home=True, old_clippers=True)
        ap = performer(a, home=False, old_clippers=True)
        if n == 5:  # no home/away flags: home comes from the title
            hp.pop("home_team"); ap.pop("away_team")
        title = f"{a['name']} at {h['name']}"
        ev = {
            "type": "nba", "id": eid, "title": title, "short_title": f"{a['short_name']} at {h['short_name']}",
            "datetime_local": f"{d}T{t}:00", "datetime_utc": utc.strftime("%Y-%m-%dT%H:%M:%S"),
            "datetime_tbd": False, "time_tbd": False,
            "venue": {"name": h["arena"], "city": h["city"], "state": h["state"], "country": "US"},
            "performers": [hp, ap] if n % 2 else [ap, hp],
            "stats": stats,
            "taxonomies": [{"name": "sports"}, {"name": "basketball"}, {"name": "nba"}],
            "url": f"https://seatgeek.com/fixture-{a['short_slug']}-at-{h['short_slug']}-tickets/{d}/{eid}",
        }
        sg_events.append(ev)
        if n == 30:  # listed twice on SeatGeek
            dup = json.loads(json.dumps(ev)); eid += 1; dup["id"] = eid
            sg_events.append(dup)

        if home in NO_TM or n == 17:  # n == 17: SeatGeek game Ticketmaster doesn't have
            continue
        tm_date = d + timedelta(days=1) if n == 23 else d   # a day apart between feeds
        key = f"{tm_date:%Y%m%d}-{away}-{home}"
        tm_games.append(tm_game(key, tm_date, t, utc, h, home, away))
        latest[key] = tm_latest(home, away, tm_date, "offsale" if n == 3 else "onsale")

    # Ticketmaster-only game (not on SeatGeek)
    d = start + timedelta(days=9)
    key = f"{d:%Y%m%d}-SAC-BOS"
    tm_games.append(tm_game(key, d, "19:30", datetime.fromisoformat(f"{d}T23:30:00"), by["BOS"], "BOS", "SAC"))
    latest[key] = tm_latest("BOS", "SAC", d, "onsale")

    # skipped by the build
    sg_events.insert(0, {
        "type": "nba", "id": 7_000_001, "title": "Preseason: Celtics at Knicks",
        "datetime_local": "2026-10-14T19:30:00", "datetime_utc": "2026-10-14T23:30:00",
        "venue": {"name": "Madison Square Garden", "city": "New York", "state": "NY"},
        "performers": [performer(by["NYK"], True), performer(by["BOS"], False)],
        "stats": {"listing_count": 10, "lowest_price": 30}, "url": "https://seatgeek.com/fixture-preseason",
    })
    sg_events.insert(5, {
        "type": "parking", "id": 7_000_002, "title": "PARKING: Lakers vs. Suns",
        "datetime_local": "2026-10-22T19:30:00", "datetime_utc": "2026-10-23T02:30:00",
        "venue": {"name": "Lot 7", "city": "Los Angeles", "state": "CA"},
        "performers": [{"name": "Crypto.com Arena Parking", "slug": "crypto-com-arena-parking"}],
        "stats": {"listing_count": 40, "lowest_price": 25}, "url": "https://seatgeek.com/fixture-parking",
    })

    per = 60
    out = FIX / "seatgeek"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("page-*.json"):
        old.unlink()
    for i in range(0, len(sg_events), per):
        page = i // per + 1
        body = {"events": sg_events[i:i + per],
                "meta": {"total": len(sg_events), "per_page": per, "page": page, "took": 3}}
        (out / f"page-{page}.json").write_text(json.dumps(body, indent=1) + "\n")

    dr = FIX / "data-repo"
    (dr / "data/tm").mkdir(parents=True, exist_ok=True)
    (dr / "config").mkdir(parents=True, exist_ok=True)
    gen = "2026-10-12T12:00:00Z"
    (dr / "data/tm/schedule.json").write_text(json.dumps(
        {"generated": gen, "season": "2026-27", "count": len(tm_games), "games": tm_games}, indent=1) + "\n")
    (dr / "data/tm/latest.json").write_text(json.dumps(
        {"generated": gen, "season": "2026-27", "games": latest}, indent=1) + "\n")
    (dr / "config/teams.json").write_text(json.dumps(
        {"season": "2026-27", "teams": [{"code": t["code"], "name": t["name"], "short_name": t["short_name"],
                                          "arena": t["arena"], "city": t["city"]} for t in teams]}, indent=1) + "\n")
    print(f"fixtures: {len(sg_events)} SeatGeek events, {len(tm_games)} Ticketmaster games")


def performer(t: dict, home: bool, old_clippers: bool = False) -> dict:
    slug = "los-angeles-clippers" if old_clippers and t["code"] == "LAC" else t["slug"]
    name = "Los Angeles Clippers" if slug == "los-angeles-clippers" else t["name"]
    p = {"name": name, "short_name": t["short_name"], "slug": slug, "type": "nba",
         "primary": True}
    p["home_team" if home else "away_team"] = True
    return p


def tm_game(key, d, t, utc, h, home, away) -> dict:
    return {
        "key": key, "season": "2026-27", "tm_id": f"FIXTURE{key.replace('-', '')}",
        "name": f"{h['name']} vs. {away}", "local_date": str(d), "local_time": f"{t}:00",
        "start_utc": utc.strftime("%Y-%m-%dT%H:%M:%SZ"), "timezone": "America/New_York",
        "venue": {"id": "FIXTUREVENUE", "name": h["arena"], "city": h["city"], "state": h["state"], "country": "US"},
        "home": home, "away": away, "neutral_site": False, "home_source": "venue",
        "url": f"https://www.ticketmaster.com/fixture-event/{key}",
        "last_seen": "2026-10-12T12:00:00Z",
    }


def tm_latest(home, away, d, status) -> dict:
    return {"home": home, "away": away, "local_date": str(d), "neutral_site": False, "listed": True,
            "ts": "2026-10-12T12:00:00Z", "status": status, "prices": [], "checked": "2026-10-12T12:00:00Z"}


if __name__ == "__main__":
    main()
