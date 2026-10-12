"""Sitemap <lastmod> that moves only when a page's content changes.

state/page-hashes.json (committed to main by the build workflow) maps each
public URL to [content hash, date]. A page keeps its date while its hash is
unchanged and gets the build date when the hash changes or the page first
appears. Price changes are content changes, so they move the date.

The hash is taken over a normalised copy of the page:
- elements with a data-volatile attribute are dropped with their content
  (the "updated <time>" stamps), so a rebuild with the same prices moves
  nothing;
- asset cache-busters (?v=<hash>) are removed, so a CSS change does not
  redate every page;
- runs of whitespace count as one space.

The file holds hashes only, never prices. Comparing hashes says "this page
changed", nothing about what a price was (CLAUDE.md rule 1).
"""

from __future__ import annotations

import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path

VOLATILE_ATTR = "data-volatile"
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "source", "track", "wbr"}
CACHE_BUSTER = re.compile(r"\?v=[0-9a-f]{6,}")


class _Stripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if self.skip:
            if tag not in VOID:
                self.skip += 1
            return
        if any(name == VOLATILE_ATTR for name, _ in attrs):
            if tag not in VOID:
                self.skip = 1
            return
        self.out.append(self.get_starttag_text() or "")

    def handle_startendtag(self, tag, attrs):
        if self.skip or any(name == VOLATILE_ATTR for name, _ in attrs):
            return
        self.out.append(self.get_starttag_text() or "")

    def handle_endtag(self, tag):
        if self.skip:
            if tag not in VOID:
                self.skip -= 1
            return
        self.out.append(f"</{tag}>")

    def _text(self, text):
        if not self.skip:
            self.out.append(text)

    handle_data = _text

    def handle_entityref(self, name):
        self._text(f"&{name};")

    def handle_charref(self, name):
        self._text(f"&#{name};")

    def handle_comment(self, data):
        self._text(f"<!--{data}-->")

    def handle_decl(self, decl):
        self._text(f"<!{decl}>")


def normalise(html: str) -> str:
    parser = _Stripper()
    parser.feed(html)
    parser.close()
    return re.sub(r"\s+", " ", CACHE_BUSTER.sub("", "".join(parser.out)))


def content_hash(html: str) -> str:
    return hashlib.sha256(normalise(html).encode("utf-8")).hexdigest()[:16]


def update(prev: dict, pages: dict[str, str], today: str) -> tuple[dict, int]:
    """New state for `pages` ({url: html}) and how many pages changed.
    URLs no longer built are dropped."""
    out, changed = {}, 0
    for url, html in pages.items():
        h = content_hash(html)
        old = prev.get(url)
        if old and old[0] == h:
            out[url] = list(old)
        else:
            out[url] = [h, today]
            changed += 1
    return out, changed


def read_state(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {u: v for u, v in data.items()
            if isinstance(v, list) and len(v) == 2 and all(isinstance(x, str) for x in v)}


def write_state(path: Path, state: dict) -> None:
    """One URL per line, sorted, so the diff shows exactly which pages moved."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = ",\n".join(f"{json.dumps(u)}: {json.dumps(v)}" for u, v in sorted(state.items()))
    path.write_text("{\n" + body + "\n}\n" if body else "{}\n", encoding="utf-8")
