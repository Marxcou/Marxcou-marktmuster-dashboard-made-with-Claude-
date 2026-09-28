"""Meldung einem Instrument zuordnen, mit belegtem Grund (match_method). Reihenfolge der Belege:
provider_tag (Anbieter nennt das Symbol) > isin (ISIN im Text) > ticker (Cashtag $AAPL oder Tickersymbol in
Großbuchstaben, mind. 3 Zeichen) > name (Firmenname ohne Rechtsform, mind. 4 Zeichen, als ganzes Wort).
Bewusst konservativ: lieber keine Zuordnung als eine falsche."""
import re
from dataclasses import dataclass

from app.adapters.base import NewsRecord
from app.adapters.news_common import company_search_name

US = ("XNYS", "XNAS")
PRIORITY = {"provider_tag": 0, "isin": 1, "ticker": 2, "name": 3}
ISIN_RE = re.compile(r"\b[A-Z]{2}[A-Z0-9]{9}[0-9]\b")


@dataclass(frozen=True)
class Candidate:
    id: int
    symbol: str
    exchange: str
    name: str
    isin: str | None


class Matcher:
    def __init__(self, instruments: list[Candidate]) -> None:
        self._by_id = {i.id: i for i in instruments}
        self._by_symbol: dict[tuple[str, str], list[Candidate]] = {}
        self._names: list[tuple[re.Pattern[str], int]] = []
        for i in instruments:
            self._by_symbol.setdefault((i.symbol.upper(), "DE" if i.exchange == "XETR" else "US"), []).append(i)
            short = company_search_name(i.name)
            if len(short) >= 4:
                self._names.append((re.compile(r"(?<![\wäöüß])" + re.escape(short) + r"(?![\wäöüß])", re.I), i.id))
        self._tickers = [(re.compile(r"(?<![\w$])\$?" + re.escape(i.symbol) + r"(?![\w])"), i.id)
                         for i in instruments if len(i.symbol) >= 3]
        self._cashtags = [(re.compile(r"\$" + re.escape(i.symbol) + r"(?![\w])"), i.id) for i in instruments]
        self._isins = {i.isin.upper(): i.id for i in instruments if i.isin}

    def match(self, rec: NewsRecord) -> dict[int, str]:
        found: dict[int, str] = {}

        def add(iid: int, method: str) -> None:
            if iid not in found or PRIORITY[method] < PRIORITY[found[iid]]:
                found[iid] = method

        for sym in rec.symbols:
            base, _, suffix = sym.upper().partition(".")
            for c in self._by_symbol.get((base, "DE" if suffix == "DE" else "US"), []):
                add(c.id, "provider_tag")
        text = f"{rec.title} {rec.excerpt}"
        for isin in ISIN_RE.findall(text):
            if isin in self._isins:
                add(self._isins[isin], "isin")
        for pat, iid in self._cashtags:
            if pat.search(text):
                add(iid, "ticker")
        for pat, iid in self._tickers:
            if pat.search(rec.title):  # Großbuchstaben, nur im Titel (Auszüge sind zu unscharf)
                add(iid, "ticker")
        for pat, iid in self._names:
            if pat.search(text):
                add(iid, "name")
        return found
