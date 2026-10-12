"""Buy links from config/affiliate.json.

While a vendor is disabled its button uses the plain event URL (SeatGeek's
event url, Ticketmaster's url from schedule.json) and StubHub is a plain
search link. An enabled vendor's template wraps that URL, usually in an
Impact tracking link: {url} is replaced by the percent-encoded event URL.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote, quote_plus

from .model import Game


@dataclass
class BuyLink:
    vendor: str
    label: str
    url: str
    sponsored: bool
    primary: bool = False


class Links:
    def __init__(self, affiliate: dict):
        self.vendors = affiliate.get("vendors") or {}

    @property
    def any_enabled(self) -> bool:
        return any(self.enabled(v) for v in self.vendors)

    def enabled(self, vendor: str) -> bool:
        v = self.vendors.get(vendor) or {}
        return bool(v.get("enabled")) and "{url}" in (v.get("template") or "")

    def wrap(self, vendor: str, url: str) -> tuple[str, bool]:
        if self.enabled(vendor):
            return self.vendors[vendor]["template"].replace("{url}", quote(url, safe="")), True
        return url, False

    def label(self, vendor: str) -> str:
        return (self.vendors.get(vendor) or {}).get("label") or vendor.title()

    def for_game(self, game: Game) -> list[BuyLink]:
        out: list[BuyLink] = []
        if game.sg and game.sg.url:
            url, sp = self.wrap("seatgeek", game.sg.url)
            out.append(BuyLink("seatgeek", self.label("seatgeek"), url, sp, primary=True))
        if game.tm and game.tm.url:
            url, sp = self.wrap("ticketmaster", game.tm.url)
            out.append(BuyLink("ticketmaster", self.label("ticketmaster"), url, sp, primary=not out))
        search = (self.vendors.get("stubhub") or {}).get("search_url")
        if search:
            q = quote_plus(f"{game.away.short_name} {game.home.short_name}")
            url, sp = self.wrap("stubhub", search.replace("{query}", q))
            out.append(BuyLink("stubhub", f"Also check {self.label('stubhub')}", url, sp))
        return out
