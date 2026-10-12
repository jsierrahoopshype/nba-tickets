# NBA tickets

Generates the HoopsMatic NBA tickets section at **https://hoopsmatic.com/tickets/**:
a hub, 30 team pages, 30 arena pages, 870 matchup pages, a road-trip planner and
a terms page. Python plus Jinja2, no front-end framework. Same structure as
[nba-watch-guide](https://github.com/jsierrahoopshype/nba-watch-guide).

`main` holds the generator. GitHub Actions builds the site every 3 hours and
force-pushes it to `gh-pages` as a single fresh commit; the hoopsmatic.com Worker
serves that branch at `/tickets/`. Pages opened straight from github.io look
unstyled, because every link and asset starts with `/tickets/`. That is expected.

Rules (SeatGeek data is never stored, attribution, footer links, wording),
data flow and secrets: see [CLAUDE.md](CLAUDE.md).

## The files you edit

| What you want to change | File |
| --- | --- |
| Parking, beer, soda, hot dog, water prices and the value-menu note per arena | `data/concessions.json` (set `status` to `"available"` once filled) |
| Affiliate links (switch a vendor on, paste its Impact template) | `config/affiliate.json` |
| Page titles, descriptions, headings, labels | `config/copy.json` |
| Whether search engines may index the section | `config/copy.json`, `launched` |
| Team names, slugs, arenas, addresses, coordinates | `config/teams.json` |
| Drivable / short-flight thresholds for the road trip | `config/distances.json` (re-run `scripts/make_distances.py` after editing coordinates) |
| Season dates, SeatGeek floor, list sizes | `config/build.json` |
| SeatGeek logo | `assets/brand/seatgeek-logo.svg` (from https://seatgeek.com/press) |

### Affiliate links

While a vendor's `enabled` is `false`, buttons use the plain SeatGeek event URL,
the Ticketmaster event URL from the data repo and a plain StubHub search. To switch
one on, set `enabled: true` and a `template` containing `{url}`, for example
`https://seatgeek.pxf.io/c/<publisher>/<ad>/<campaign>?u={url}`. The URL is
percent-encoded into `{url}`. As soon as any vendor is enabled, every page shows
"HoopsMatic may earn a commission when you buy through links on this page." at
the top, and those buttons get `rel="sponsored"`.

### Concessions

`data/concessions.json` has one entry per team, all `"not available"` for now.
Fill in USD numbers (`14.5`), `source_url` and `last_checked` (`YYYY-MM-DD`), and
set `status` to `"available"`. The family-of-four estimate (4 get-in tickets +
parking + 2 beers + 2 sodas + 4 hot dogs, for the cheapest game at the arena)
appears once parking, beer, soda and hot dog are all filled in.

## Setup (once)

1. Actions secrets in this repo: `SEATGEEK_CLIENT_ID` and `DATA_REPO_TOKEN`
   (fine-grained PAT, Contents: read-only on `nba-tickets-data`).
2. Settings → Pages: deploy from the `gh-pages` branch, root. The first build
   creates the branch.
3. Settings → Actions → General → Workflow permissions: read and write (the build
   pushes `gh-pages` and the report).

## Running it locally

```
pip install -r requirements.txt pytest
python -m pytest
python -m tickets build --offline --out site          # fixtures, no API keys
```

A live build needs `SEATGEEK_CLIENT_ID` in the environment and a checkout of
`nba-tickets-data`: `python -m tickets build --out site --data-dir ../nba-tickets-data`.
Only run that if you mean to write `state/page-hashes.json` and
`reports/last-build.md` locally.

## What each build writes

- `site/` (published to `gh-pages`, never committed to `main`): HTML,
  `sitemap.xml`, CSS, JS, fonts, team logos.
- `reports/last-build.md`: SeatGeek event count, games matched with
  Ticketmaster, unmatched games, pages rendered. Counts and game keys only.
- `state/page-hashes.json`: one content hash and date per URL, for sitemap
  `<lastmod>`. No prices.
