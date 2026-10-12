# Offline fixtures

Synthetic data for `python -m tickets build --offline` and the tests. Nothing
here was recorded from SeatGeek or Ticketmaster: every price, id and URL is
made up by `scripts/make_fixtures.py` (seeded, so it regenerates identically).

- `seatgeek/page-*.json`: a two-page SeatGeek `/2/events` response (110 events,
  15 game days from Oct 20, 2026), with the edge cases listed at the top of the
  script.
- `data-repo/`: the three files the build reads from the private
  `nba-tickets-data` repo, in the same layout (`data/tm/schedule.json`,
  `data/tm/latest.json`, `config/teams.json`), also synthetic.

Regenerate after changing `config/teams.json`: `python scripts/make_fixtures.py`.
