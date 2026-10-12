"""The rendered site: page set, SEO fields, legal rules from CLAUDE.md."""
from __future__ import annotations

import json
import re

from tickets import config
from tickets.build import EXPECTED_PAGES

from conftest import pages


def test_page_set(site):
    site_dir, res = site
    found = pages(site_dir)
    assert len(found) == EXPECTED_PAGES == 933
    rels = {p.parent.relative_to(site_dir).as_posix() for p in found}
    for rel in (".", "los-angeles-lakers", "la-clippers", "arenas/crypto-com-arena", "lakers-at-grizzlies",
                "grizzlies-at-lakers", "76ers-at-trail-blazers", "road-trip", "terms"):
        assert rel in rels, rel
    assert res.pages == {"hub": 1, "team": 30, "arena": 30, "matchup": 870, "road_trip": 1, "terms": 1}


def test_canonical_and_og_url_on_hoopsmatic(site):
    site_dir, _ = site
    for p in pages(site_dir):
        html = p.read_text()
        rel = p.parent.relative_to(site_dir).as_posix()
        want = config.public_url("" if rel == "." else rel + "/")
        assert f'<link rel="canonical" href="{want}">' in html, p
        assert f'<meta property="og:url" content="{want}">' in html, p
        assert "github.io" not in html


def test_noindex_while_not_launched(site):
    site_dir, res = site
    for p in pages(site_dir):
        assert '<meta name="robots" content="noindex,follow">' in p.read_text(), p
    sitemap = (site_dir / "sitemap.xml").read_text()
    assert "<loc>" not in sitemap
    assert res.sitemap_urls == 0


def test_launched_sitemap_and_robots(launched_site):
    site_dir, res, state = launched_site
    hub = (site_dir / "index.html").read_text()
    assert "noindex" not in hub
    sitemap = (site_dir / "sitemap.xml").read_text()
    locs = re.findall(r"<loc>([^<]+)</loc><lastmod>(\d{4}-\d{2}-\d{2})</lastmod>", sitemap)
    assert locs and all(u.startswith("https://hoopsmatic.com/tickets/") for u, _ in locs)
    # A pairing with no games left is noindex and kept out of the sitemap.
    empty = [p for p in pages(site_dir) if "left this season</h2>" in p.read_text() and
             re.search(r"<h2>0 games left", p.read_text())]
    assert empty, "fixtures should leave some pairings without games"
    for p in empty:
        html = p.read_text()
        assert 'content="noindex,follow"' in html
        canonical = re.search(r'rel="canonical" href="([^"]+)"', html).group(1)
        assert canonical not in sitemap
    assert len(locs) == res.sitemap_urls == len(pages(site_dir)) - len(empty)


def test_no_data_files_published(site):
    """Rule 1: SeatGeek numbers live only in HTML. No JSON or CSV on the site."""
    site_dir, _ = site
    allowed = {".html", ".xml", ".css", ".js", ".svg", ".woff2", ".txt", ".png", ""}
    for p in site_dir.rglob("*"):
        if p.is_file():
            assert p.suffix not in (".json", ".csv"), p
            assert p.suffix in allowed, p


def test_seatgeek_attribution_wherever_prices_show(site):
    site_dir, _ = site
    for p in pages(site_dir):
        html = p.read_text()
        if re.search(r'class="(p|v[^"]*|num)">\$', html) or "rt-data" in html:
            assert '<a class="sg-logo" href="https://seatgeek.com"' in html, p
            assert "Prices by SeatGeek, updated <time" in html, p


def test_footer_links_everywhere(site):
    site_dir, _ = site
    for p in pages(site_dir):
        html = p.read_text()
        assert 'href="https://hoopsmatic.com/privacy"' in html, p
        assert 'href="/tickets/terms/"' in html, p


def test_never_lowest_anywhere(site):
    site_dir, _ = site
    bad = re.compile(r"(lowest|cheapest|best) (price )?anywhere|lowest price online|guaranteed lowest", re.I)
    for p in pages(site_dir):
        assert not bad.search(p.read_text()), p
    assert not bad.search((config.ROOT / "config/copy.json").read_text().split('"launched"')[1])


def test_no_affiliate_disclosure_while_disabled(site):
    site_dir, _ = site
    for p in pages(site_dir):
        html = p.read_text()
        assert "may earn a commission when you buy through links on this page" not in html
        assert "sponsored nofollow" not in html


def test_titles_and_descriptions_unique_and_short(site):
    site_dir, _ = site
    titles, descs = set(), set()
    for p in pages(site_dir):
        html = p.read_text()
        t = re.search(r"<title>(.*?)</title>", html).group(1)
        d = re.search(r'<meta name="description" content="(.*?)">', html).group(1)
        assert len(t.replace("&amp;", "&")) <= 60 and len(d.replace("&amp;", "&").replace("&#39;", "'")) <= 155, p
        titles.add(t)
        descs.add(d)
    assert len(titles) == len(descs) == EXPECTED_PAGES


def test_jsonld_sports_events_without_prices(site):
    site_dir, _ = site
    html = (site_dir / "nuggets-at-lakers/index.html").read_text()
    raw = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1)
    data = json.loads(raw)
    events = data["@graph"]
    assert events and all(e["@type"] == "SportsEvent" for e in events)
    assert '"offers"' not in raw and "price" not in raw.lower()
    assert events[0]["location"]["address"]["streetAddress"]


def test_road_trip_embeds_its_data(site):
    site_dir, _ = site
    html = (site_dir / "road-trip/index.html").read_text()
    raw = re.search(r'<script type="application/json" id="rt-data">(.*?)</script>', html, re.S).group(1)
    data = json.loads(raw)
    assert len(data["games"]) > 50
    assert set(data["teams"]) == set(data["miles"])
    assert data["drivable"] == 400


def test_matchup_links(site):
    site_dir, _ = site
    html = (site_dir / "lakers-at-grizzlies/index.html").read_text()
    assert 'href="/tickets/grizzlies-at-lakers/"' in html
    assert "https://hoopsmatic.com/how-to-watch/los-angeles-lakers" in html
    assert "https://hoopsmatic.com/how-to-watch/memphis-grizzlies" in html


def test_no_tm_teams_show_seatgeek_only(site):
    site_dir, _ = site
    html = (site_dir / "cleveland-cavaliers/index.html").read_text()
    home = html.split('id="home"')[1].split('id="road"')[0]
    assert "ticketmaster.com" not in home
    assert "SeatGeek only" in home


def test_terms_page(site):
    site_dir, _ = site
    html = (site_dir / "terms/index.html").read_text()
    body = re.sub(r"<[^>]+>", " ", html.split('<div class="prose">')[1].split("</div>")[0])
    assert len(body.split()) < 300
    assert "SeatGeek Inc. and its affiliates are third-party beneficiaries" in body
    assert "commission" in body


def test_titles_stand_alone(site):
    """Design rule: no eyebrow or kicker line above or beside any title."""
    site_dir, _ = site
    for p in pages(site_dir):
        html = p.read_text()
        assert 'class="brand"' not in html, p
        hdr = re.search(r'<header class="hdr">(.*?)</header>', html, re.S).group(1)
        assert re.sub(r"<img[^>]*>|<span class=\"lg[^\"]*\"[^>]*>[A-Z]{3}</span>", "", hdr).strip().startswith("<h1>"), p
        assert hdr.strip().endswith("</h1>"), p
        for head in re.findall(r'<div class="block-head">(.*?)</div>', html, re.S):
            assert re.fullmatch(r"\s*<h2>[^<]*</h2>\s*", head), (p, head)
