# CLAUDE.md

Standing rules for this repo: the HoopsMatic NBA tickets section, served at
https://hoopsmatic.com/tickets/ (the hoopsmatic-worker proxies that path to this
repo's GitHub Pages). Check every rule before reporting any PR.

## Legal rules (from SeatGeek's and Ticketmaster's API terms; do not break)

1. **SeatGeek data is displayed, never stored.** It is fetched during the build,
   rendered into the pages and dropped. Never write a raw SeatGeek response, or
   any SeatGeek number, to a file that is committed or published. The only
   places SeatGeek numbers may live are the rendered HTML and the JSON embedded
   inside the road-trip page (`#rt-data`). No separate JSON/CSV data files on
   the site (`scripts/publish.sh` refuses to publish one). No comparison against
   earlier builds: no "price dropped", no history, no caches of earlier
   responses. The sitemap's page-hash check is the one exception the owner asked
   for: it stores a hash per page, which says that a page changed, never what a
   price was.
2. **gh-pages never accumulates price history.** Every build force-pushes it as a
   single-commit orphan branch (`scripts/publish.sh`). Never publish any other way.
3. **SeatGeek attribution wherever SeatGeek prices appear:** the SeatGeek logo
   linking to https://seatgeek.com, plus "Prices by SeatGeek, updated <time>"
   (`sg_attrib` in `templates/partials/macros.html`). Never imply SeatGeek
   endorses HoopsMatic. The official logo file goes in
   `assets/brand/seatgeek-logo.svg` (or `.png`), downloaded from
   https://seatgeek.com/press; until it is there the build shows a plain
   "SeatGeek" text badge in its place.
4. **Every page footer links** to https://hoopsmatic.com/privacy and to the terms
   page (/tickets/terms/).
5. **Never "lowest anywhere".** SeatGeek's `lowest_price` is "the lowest listed on
   SeatGeek". Nothing on the site states a price is the lowest anywhere.

Tests that guard these: `tests/test_site.py` (attribution, footer, no data
files, wording) and `tests/test_data.py` (state/report hold no SeatGeek numbers,
`tickets/seatgeek.py` writes nothing, workflow and publish rules).

## Data flow

```
GitHub Actions (.github/workflows/build.yml, every 3 h, on push to main, manual)
  ├─ pytest against fixtures/ (offline)
  ├─ actions/checkout nba-tickets-data → _data/   (DATA_REPO_TOKEN, read-only)
  │     data/tm/schedule.json   Ticketmaster games + event URLs
  │     data/tm/latest.json     on-sale / off-sale status, "checked" time
  │     config/teams.json       arena names (cross-checked against ours)
  ├─ python -m tickets build --out site --data-dir _data
  │     SeatGeek /2/events?taxonomies.name=nba (SEATGEEK_CLIENT_ID), ~13 pages,
  │       in memory only (tickets/seatgeek.py)
  │     merge on <date>-<away>-<home> with Ticketmaster (tickets/merge.py)
  │     prices maths (tickets/stats.py), buy links (tickets/links.py)
  │     render 933 pages (templates/), sitemap.xml, copy assets
  │     team logos from jsierrahoopshype/nba-headshots copied into site/assets/logos
  ├─ scripts/publish.sh site gh-pages        checks, then orphan force-push
  └─ scripts/commit-report.sh                reports/last-build.md +
                                             state/page-hashes.json → main [skip ci]
```

- The build fails, and nothing is published, when SeatGeek returns fewer NBA
  regular-season games than the floor: `min(900, 0.75 x games still to play)`
  (config/build.json). A flat 900 would fail every build from early December,
  because SeatGeek only lists games that haven't been played.
- CLE, HOU, MIN, NOP and UTA have no Ticketmaster home games: their home games
  show SeatGeek (and the StubHub search) only, and are not counted as unmatched.
- The report lists counts and game keys only, never prices.
- Two runs can build the same commit back to back (GitHub started two runs for
  the merge of PR #1; a schedule can also fire right after a push). So the build
  first takes `state/page-hashes.json` from the tip of main, and
  `scripts/commit-report.sh` never rebases: it resets to the tip of main and puts
  this build's two files on top (`tests/test_commit_report.py`).

## Secrets

| Name | Where | Used for |
|---|---|---|
| `SEATGEEK_CLIENT_ID` | this repo, Actions secret | SeatGeek Platform API |
| `DATA_REPO_TOKEN` | this repo, Actions secret | read-only fine-grained PAT for jsierrahoopshype/nba-tickets-data (Contents: read). It never expires. |
| `GITHUB_TOKEN` | automatic | push gh-pages, commit the report to main |

Never print, commit or log any of them. `tickets/seatgeek.py` scrubs the client id
from error messages.

## Pages and URLs (never change a slug without being asked)

- `/tickets/` hub
- `/tickets/<team-slug>/` 30 team pages (slugs match How to Watch, e.g. `la-clippers`)
- `/tickets/arenas/<arena-slug>/` 30 arena pages
- `/tickets/<away-short>-at-<home-short>/` 870 matchup pages (`lakers-at-grizzlies`)
- `/tickets/road-trip/`, `/tickets/terms/`

Slugs live in `config/teams.json`. Canonical and og:url are always
`https://hoopsmatic.com/tickets/...`, never github.io.

## SEO

- `config/copy.json` `launched: false` → every page has `noindex,follow` and
  `sitemap.xml` lists no URLs. Page hashes are tracked anyway so lastmod dates
  are right on launch day.
- Once launched, a matchup with no games left is noindex and out of the sitemap.
- `<lastmod>` moves only when the page's content hash changes
  (`tickets/lastmod.py`); the "updated" stamps are `data-volatile` and left out.
- JSON-LD `SportsEvent` on matchup pages, without offers or prices.

## Working here

- Tests: `python -m pytest`.
- Offline build: `python -m tickets build --offline --out site` (add `--no-logos`
  with no network; `--today 2026-10-12` to pin the date). It writes its hash file
  and report to `.offline/`, never to `state/` or `reports/`.
- Regenerate fixtures: `python scripts/make_fixtures.py`. Distance table:
  `python scripts/make_distances.py`.
- Never publish (push gh-pages) from a session. Publishing is the workflow's job.
- Every report ends with the tip SHA and a "Decisions for Jorge" section (or "None").
