"""Parsing, merging, maths, lastmod, affiliate links and the SeatGeek floor."""
from __future__ import annotations

import copy as _copy
import json
import re
from datetime import date

import pytest

from tickets import config
from tickets.build import BuildError
from tickets.links import Links
from tickets.merge import required_events
from tickets.model import load_teams
from tickets.seatgeek import load_fixture, parse_events
from tickets.stats import family_of_four

from conftest import FIX, run_build, pages


def raw():
    return load_fixture(FIX / "seatgeek")


def test_parse_handles_edge_cases():
    s = config.load_settings()
    res = parse_events(raw(), load_teams(s.teams_raw), s.build)
    assert res.skipped == {"not two NBA teams": 1, "outside the regular season": 1}
    homes = {g.home.code for g in res.games}
    assert "LAC" in homes or "LAC" in {g.away.code for g in res.games}  # old slug still matches
    assert any(g.home_from == "title" for g in res.games)
    assert any(not g.stats.priced for g in res.games)


def test_merge_counts(site):
    _, res = site
    m = res.merged
    assert m.matched == 89
    assert m.sg_only_no_tm_team == 17
    assert m.sg_unmatched == ["20261022-SAC-POR"]
    assert m.tm_unmatched == ["20261029-SAC-BOS"]
    assert m.shifted == ["20261023-PHX-ATL ~ 20261024-PHX-ATL"]
    assert len(m.duplicates) == 1


def test_floor_scales_with_the_season():
    b = config.load_settings().build
    assert required_events(date(2026, 10, 12), b) == 900
    assert required_events(date(2026, 10, 20), b) == 900
    assert 0 < required_events(date(2027, 2, 1), b) < 900
    assert required_events(date(2027, 5, 1), b) == 0


def test_build_fails_below_floor(tmp_path):
    with pytest.raises(BuildError, match="fewer than the floor of 900"):
        run_build(tmp_path / "site", tmp_path / "h.json", min_events=None)
    assert not (tmp_path / "site").exists()


def test_lastmod_moves_only_on_content_change(tmp_path):
    state = tmp_path / "hashes.json"
    first = run_build(tmp_path / "a", state)
    assert first.changed == 933
    before = json.loads(state.read_text())
    # Same data an hour later: the "updated" stamp changes, nothing else.
    from datetime import datetime, timezone
    later = datetime(2026, 10, 13, 14, 0, tzinfo=timezone.utc)
    again = run_build(tmp_path / "b", state, today=date(2026, 10, 12), now=later)
    assert again.changed == 0
    assert json.loads(state.read_text()) == before
    # One price changes: that game's pages move, with the new date.
    events = raw()
    target = next(e for e in events if e.get("title") == "Denver Nuggets at Los Angeles Lakers")
    target["stats"]["lowest_price"] += 7
    third = run_build(tmp_path / "c", state, raw=events, today=date(2026, 10, 13))
    after = json.loads(state.read_text())
    moved = {u for u in after if after[u] != before[u]}
    assert "https://hoopsmatic.com/tickets/nuggets-at-lakers/" in moved
    assert "https://hoopsmatic.com/tickets/los-angeles-lakers/" in moved
    assert "https://hoopsmatic.com/tickets/terms/" not in moved
    assert all(after[u][1] == "2026-10-13" for u in moved)
    assert third.changed == len(moved)


def test_state_and_report_hold_no_seatgeek_numbers(tmp_path):
    from tickets import report
    from datetime import datetime, timezone
    state = tmp_path / "hashes.json"
    res = run_build(tmp_path / "s", state)
    for url, (h, d) in json.loads(state.read_text()).items():
        assert re.fullmatch(r"[0-9a-f]{16}", h) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d)
    rp = tmp_path / "last-build.md"
    report.write(rp, res, datetime(2026, 10, 12, tzinfo=timezone.utc), "offline fixtures", None)
    text = rp.read_text()
    assert "$" not in text and "seatgeek.com" not in text
    assert "Games matched between SeatGeek and Ticketmaster: 89" in text


def test_affiliate_enabled_wraps_links_and_shows_disclosure(tmp_path):
    s = config.load_settings()
    s.affiliate = _copy.deepcopy(s.affiliate)
    s.affiliate["vendors"]["seatgeek"].update(enabled=True, template="https://seatgeek.pxf.io/c/1/2/3?u={url}")
    run_build(tmp_path / "site", tmp_path / "h.json", settings=s)
    for p in pages(tmp_path / "site"):
        html = p.read_text()
        assert '<p class="disclosure">HoopsMatic may earn a commission when you buy through links on this page.</p>' in html
    lakers = (tmp_path / "site/los-angeles-lakers/index.html").read_text()
    assert 'href="https://seatgeek.pxf.io/c/1/2/3?u=https%3A%2F%2Fseatgeek.com%2F' in lakers
    assert 'rel="sponsored nofollow noopener"' in lakers
    # Ticketmaster stays plain while it is disabled.
    assert re.search(r'href="https://www.ticketmaster.com/[^"]+" target="_blank" rel="nofollow noopener"', lakers)


def test_links_disabled_without_template():
    links = Links({"vendors": {"seatgeek": {"enabled": True, "template": ""}}})
    assert not links.any_enabled


def test_family_of_four():
    assert family_of_four(50, {"status": "not available"}) is None
    con = {"status": "available", "parking": 30, "beer": 14, "soda": 7, "hot_dog": 8}
    fam = family_of_four(50, con)
    assert fam["total"] == 4 * 50 + 30 + 2 * 14 + 2 * 7 + 4 * 8


def test_concessions_file_complete():
    con = json.loads((config.ROOT / "data/concessions.json").read_text())["teams"]
    assert len(con) == 30
    keys = {"arena", "status", "parking", "beer", "soda", "hot_dog", "water", "value_menu_note",
            "source_url", "last_checked"}
    for code, entry in con.items():
        assert set(entry) == keys, code
        assert entry["status"] in ("available", "not available")


def test_seatgeek_module_writes_nothing():
    """Rule 1: the SeatGeek code never writes to disk."""
    src = (config.ROOT / "tickets/seatgeek.py").read_text()
    for needle in ("write_text", "write_bytes", "open(", "json.dump(", "shelve", "pickle", "sqlite"):
        assert needle not in src, needle


def test_workflow_rules():
    wf = (config.ROOT / ".github/workflows/build.yml").read_text()
    assert "cron: '41 */3 * * *'" in wf
    assert "workflow_dispatch" in wf and "branches: [main]" in wf
    assert "DATA_REPO_TOKEN" in wf and "SEATGEEK_CLIENT_ID" in wf
    pub = (config.ROOT / "scripts/publish.sh").read_text()
    assert "git init" in pub and "--force" in pub
    commit = (config.ROOT / "scripts/commit-report.sh").read_text()
    assert "[skip ci]" in commit
    assert "git add reports/last-build.md state/page-hashes.json" in commit
