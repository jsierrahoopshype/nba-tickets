"""Offline builds from fixtures/, shared by the tests."""
from __future__ import annotations

import copy as _copy
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from tickets import config
from tickets.build import build
from tickets.merge import load_tm
from tickets.seatgeek import load_fixture

FIX = config.ROOT / "fixtures"
TODAY = date(2026, 10, 12)
NOW = datetime(2026, 10, 12, 13, 0, tzinfo=timezone.utc)


def run_build(out: Path, state: Path, settings=None, raw=None, today=TODAY, now=NOW, min_events=0):
    settings = settings or config.load_settings()
    raw = raw if raw is not None else load_fixture(FIX / "seatgeek")
    tm = load_tm(FIX / "data-repo")
    return build(out, settings, raw, tm, today, now, state, logos=False, min_events=min_events)


@pytest.fixture(scope="session")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("build")
    res = run_build(root / "site", root / "hashes.json")
    return root / "site", res


@pytest.fixture(scope="session")
def launched_site(tmp_path_factory):
    root = tmp_path_factory.mktemp("launched")
    settings = config.load_settings()
    settings.copy = _copy.deepcopy(settings.copy)
    settings.copy["launched"] = True
    res = run_build(root / "site", root / "hashes.json", settings=settings)
    return root / "site", res, root / "hashes.json"


def pages(site_dir: Path):
    return sorted(site_dir.rglob("index.html"))
