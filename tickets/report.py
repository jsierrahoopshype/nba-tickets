"""reports/last-build.md: what the last build saw and wrote.

Counts and game keys only. No SeatGeek prices, listing counts or URLs ever go
in here: this file is committed to main (CLAUDE.md rule 1).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .build import BuildResult


def write(path: Path, res: BuildResult, now: datetime, mode: str, commit: str | None) -> None:
    m, p = res.merged, res.parsed
    lines = [
        "# Last build",
        "",
        f"- Built: {now:%Y-%m-%d %H:%M} UTC ({mode})" + (f", commit `{commit[:7]}`" if commit else ""),
        f"- SeatGeek events returned: {p.raw_count}",
        f"- NBA regular-season games found on SeatGeek: {len(p.games)} (floor this build: {res.required})",
    ]
    for reason, n in sorted(p.skipped.items()):
        lines.append(f"  - skipped, {reason}: {n}")
    lines += [
        f"- Ticketmaster schedule generated: {res.tm_generated or 'unknown'}; status last checked: {res.tm_checked or 'unknown'}",
        f"- Games matched between SeatGeek and Ticketmaster: {m.matched}",
        f"- SeatGeek only, home team has no Ticketmaster games (CLE, HOU, MIN, NOP, UTA): {m.sg_only_no_tm_team}",
        f"- SeatGeek games with no Ticketmaster match: {len(m.sg_unmatched)}",
        f"- Ticketmaster games with no SeatGeek match: {len(m.tm_unmatched)}",
        f"- Matched one day apart: {len(m.shifted)}",
        f"- Duplicate SeatGeek games dropped: {len(m.duplicates)}",
        f"- Team logos copied: {res.logos} of 30",
        "",
        "## Pages",
        "",
    ]
    total = sum(res.pages.values())
    for kind in ("hub", "team", "arena", "matchup", "road_trip", "terms"):
        lines.append(f"- {kind}: {res.pages.get(kind, 0)}")
    lines += [
        f"- total: {total}",
        f"- noindex: {res.noindex}",
        f"- sitemap URLs: {res.sitemap_urls}",
        f"- pages whose content changed (lastmod moved): {res.changed}",
        "",
    ]

    def block(title: str, keys: list[str]) -> None:
        lines.append(f"## {title} ({len(keys)})")
        lines.append("")
        lines.extend(f"- {k}" for k in keys[:200]) if keys else lines.append("None.")
        if len(keys) > 200:
            lines.append(f"- … and {len(keys) - 200} more")
        lines.append("")

    block("Unmatched SeatGeek games", m.sg_unmatched)
    block("Unmatched Ticketmaster games", m.tm_unmatched)
    block("Matched one day apart", m.shifted)
    block("Arena names that differ from the data repo", res.arena_mismatch)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
