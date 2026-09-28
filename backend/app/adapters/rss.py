"""RSS/Atom-Feeds seriöser Medien und EQS-Ad-hoc-Meldungen. Jeder Feed ist eine eigene Quelle.
Es werden nur Überschrift, ein kurzer Auszug und der Link übernommen.

Feeds sind standardmäßig ausgeschaltet: Adresse und Nutzungsbedingungen jedes Feeds müssen vor der Freischaltung
geprüft werden (Plan: 'nicht gescrapt, wenn die Bedingungen es verbieten'). Freischalten per .env:
RSS_ENABLED_FEEDS=tagesschau,cnbc (oder 'all'); EQS über EQS_RSS_URL. Die Adressen unten sind Vorschläge und
wurden in dieser Umgebung nicht abgerufen; ein falscher Link zeigt sich als Status 'offline' auf der Seite Quellen."""
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from defusedxml import ElementTree as ET

from app.adapters.base import AdapterMetadata, NewsAdapter, NewsRecord
from app.adapters.http import ProbedHealth, ResilientHttp, SourceError
from app.adapters.news_common import clean_excerpt, clean_title
from app.config import get_settings


@dataclass(frozen=True)
class FeedConfig:
    id: str
    name: str
    url: str
    homepage: str
    terms_url: str
    language: str
    description: str
    poll_seconds: int = 600
    is_official: bool = False


FEEDS: tuple[FeedConfig, ...] = (
    FeedConfig("tagesschau", "tagesschau.de Wirtschaft", "https://www.tagesschau.de/wirtschaft/index~rss2.xml",
               "https://www.tagesschau.de", "https://www.tagesschau.de/infoservices/rssfeeds", "de",
               "Wirtschaftsmeldungen der ARD-Tagesschau (allgemeine Marktnachrichten, ohne feste Aktienzuordnung)."),
    FeedConfig("cnbc", "CNBC Top News", "https://www.cnbc.com/id/100003114/device/rss/rss.html",
               "https://www.cnbc.com", "https://www.cnbc.com/nbcuniversal-terms-of-service/", "en",
               "Allgemeine US-Finanz- und Unternehmensnachrichten von CNBC."),
    FeedConfig("marketwatch", "MarketWatch Top Stories", "https://feeds.content.dowjones.io/public/rss/mw_topstories",
               "https://www.marketwatch.com", "https://www.marketwatch.com/site/rss", "en",
               "Allgemeine US-Marktnachrichten von MarketWatch."),
    FeedConfig("handelsblatt", "Handelsblatt Finanzen", "https://www.handelsblatt.com/contentexport/feed/finanzen",
               "https://www.handelsblatt.com", "https://www.handelsblatt.com/hilfe/rss", "de",
               "Deutsche Finanz- und Unternehmensnachrichten des Handelsblatts."),
)
EQS = FeedConfig("eqs", "EQS-News (Ad-hoc-Meldungen)", "", "https://www.eqs-news.com",
                 "https://www.eqs-news.com/terms-of-use/", "de",
                 "Ad-hoc-Mitteilungen und Pflichtveröffentlichungen deutscher Unternehmen (EQS, früher DGAP).",
                 poll_seconds=300, is_official=True)


def _text(el: Any, tag: str, ns: str = "") -> str:
    node = el.find(f"{ns}{tag}")
    return (node.text or "").strip() if node is not None and node.text else ""


def parse_feed(xml: bytes, source_key: str, language: str | None, fetched: datetime) -> list[NewsRecord]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise SourceError("Feed ist kein gültiges XML") from exc
    atom = "{http://www.w3.org/2005/Atom}"
    out: list[NewsRecord] = []
    if root.tag == f"{atom}feed":
        for e in root.findall(f"{atom}entry"):
            link_el = e.find(f"{atom}link")
            url = (link_el.get("href") if link_el is not None else "") or ""
            date = _text(e, "published", atom) or _text(e, "updated", atom)
            ts = datetime.fromisoformat(date.replace("Z", "+00:00")) if date else None
            if url and ts and _text(e, "title", atom):
                out.append(NewsRecord(external_id=_text(e, "id", atom) or url, url=url,
                                      title=clean_title(_text(e, "title", atom)),
                                      excerpt=clean_excerpt(_text(e, "summary", atom)),
                                      published_at=ts if ts.tzinfo else ts.replace(tzinfo=UTC), fetched_at=fetched,
                                      source_key=source_key, language=language))
        return out
    for item in root.iter("item"):
        url, title, date = _text(item, "link"), _text(item, "title"), _text(item, "pubDate")
        if not (url and title and date):
            continue  # ohne Link oder Zeitpunkt nicht belegbar, also verworfen
        try:
            ts = parsedate_to_datetime(date)
        except (TypeError, ValueError):
            continue
        out.append(NewsRecord(external_id=_text(item, "guid") or url, url=url, title=clean_title(title),
                              excerpt=clean_excerpt(_text(item, "description")),
                              published_at=ts if ts.tzinfo else ts.replace(tzinfo=UTC), fetched_at=fetched,
                              source_key=source_key, language=language))
    return out


class RssFeedAdapter(ProbedHealth, NewsAdapter):
    def __init__(self, feed: FeedConfig, *, enabled: bool, url: str | None = None,
                 transport: httpx.BaseTransport | None = None, **kw: Any) -> None:
        self.feed = feed
        self.key = "eqs_news" if feed.id == "eqs" else f"rss_{feed.id}"
        self.poll_seconds = feed.poll_seconds
        self._url = url or feed.url
        self._enabled = enabled and bool(self._url)
        self.disabled_reason = (
            "EQS_RSS_URL nicht gesetzt (Feed-Adresse und Nutzungsbedingungen zuerst prüfen)" if feed.id == "eqs"
            else f"Nicht freigeschaltet (Nutzungsbedingungen prüfen, dann RSS_ENABLED_FEEDS={feed.id} setzen)")
        self.http = ResilientHttp(base_url="", headers={"User-Agent": "Marktmuster-Dashboard (Informationstool)"},
                                  rate_per_min=6, transport=transport, **kw)

    def metadata(self) -> AdapterMetadata:
        f = self.feed
        return AdapterMetadata(
            key=self.key, name=f.name, kind="news",
            description=f"{f.description} Nur Überschrift, kurzer Auszug und Link.", homepage=f.homepage,
            terms_url=f.terms_url, update_interval=f"alle {f.poll_seconds // 60} Min.", delay_text="Minuten",
            requires_key=False, is_official=f.is_official)

    def is_configured(self) -> bool:
        return self._enabled

    def _probe(self) -> None:
        self.http.request("GET", self._url)

    def fetch_news(self, symbols: list[str], since: datetime) -> list[NewsRecord]:
        resp = self.http.request("GET", self._url)
        records = parse_feed(resp.content, self.key, self.feed.language, datetime.now(UTC))
        return [r for r in records if r.published_at >= since]


def build_rss_adapters() -> list[RssFeedAdapter]:
    s = get_settings()
    wanted = {x.strip() for x in s.rss_enabled_feeds.split(",") if x.strip()}
    adapters = [RssFeedAdapter(f, enabled="all" in wanted or f.id in wanted) for f in FEEDS]
    adapters.append(RssFeedAdapter(EQS, enabled=bool(s.eqs_rss_url), url=s.eqs_rss_url))
    return adapters
