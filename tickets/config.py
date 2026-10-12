"""Paths, URLs and the config files under config/ and data/."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://hoopsmatic.com"
BASE_PATH = "/tickets/"
SEATGEEK_HOME = "https://seatgeek.com"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def site_path(rel: str = "") -> str:
    """Root-relative URL inside the section: site_path('lakers-at-grizzlies/')."""
    return BASE_PATH + rel.lstrip("/")


def public_url(rel: str = "") -> str:
    """Absolute hoopsmatic.com URL, used for canonical, og:url and the sitemap.
    Never github.io."""
    return BASE_URL + site_path(rel)


@dataclass
class Settings:
    copy: dict
    build: dict
    affiliate: dict
    teams_raw: dict
    distances: dict
    concessions: dict
    extra: dict = field(default_factory=dict)

    @property
    def launched(self) -> bool:
        return bool(self.copy.get("launched"))


def load_settings(root: Path = ROOT) -> Settings:
    return Settings(
        copy=load_json(root / "config/copy.json"),
        build=load_json(root / "config/build.json"),
        affiliate=load_json(root / "config/affiliate.json"),
        teams_raw=load_json(root / "config/teams.json"),
        distances=load_json(root / "config/distances.json"),
        concessions=load_json(root / "data/concessions.json"),
    )
