"""GDELT DOC 2.0 (kostenlos, ohne Schlüssel): breite globale Abdeckung, auch deutschsprachige Medien.
GDELT liefert nur Überschrift, Link und Domain; Meldungen ohne belegte Zuordnung (Ticker oder Firmenname im Titel)
werden verworfen, weil die Quelle sonst zu verrauscht wäre."""
from datetime import UTC, datetime
from typing import Any

import httpx

from app.adapters.base import AdapterMetadata, NewsAdapter, NewsRecord, NewsTarget
from app.adapters.http import ProbedHealth, ResilientHttp, SourceError
from app.adapters.news_common import clean_title, company_search_name

LANG = {"English": "en", "German": "de"}
MAX_TARGETS_PER_RUN = 8


class GdeltAdapter(ProbedHealth, NewsAdapter):
    key = "gdelt"
    poll_seconds = 900
    require_match = True

    def __init__(self, transport: httpx.BaseTransport | None = None, **kw: Any) -> None:
        self.http = ResilientHttp(base_url="https://api.gdeltproject.org", rate_per_min=10, transport=transport, **kw)
        self._cursor = 0

    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            key=self.key, name="GDELT", kind="news",
            description="Weltweite Nachrichtenerfassung (Projekt GDELT). Verrauscht: Meldungen werden nur behalten, "
            "wenn Firmenname oder Ticker im Titel steht. Nur Überschrift, Link und Domain.",
            homepage="https://www.gdeltproject.org", terms_url="https://www.gdeltproject.org/about.html",
            update_interval="alle 15 Min. (reihum)", delay_text="ca. 15 Min.", requires_key=False,
        )

    def _probe(self) -> None:
        self.http.request("GET", "/api/v2/doc/doc", params={"query": "markets", "mode": "artlist",
                                                              "format": "json", "maxrecords": 1})

    def fetch_news(self, symbols: list[str], since: datetime) -> list[NewsRecord]:
        return []  # GDELT sucht nach Namen, siehe fetch_news_for

    def fetch_news_for(self, targets: list[NewsTarget], since: datetime) -> list[NewsRecord]:
        if not targets:
            return []
        start = self._cursor % len(targets)
        batch = (targets[start:] + targets[:start])[:MAX_TARGETS_PER_RUN]
        self._cursor += MAX_TARGETS_PER_RUN
        out: list[NewsRecord] = []
        for t in batch:
            name = company_search_name(t.name)
            if len(name) < 3:
                continue
            resp = self.http.request("GET", "/api/v2/doc/doc", params={
                "query": f'"{name}"', "mode": "artlist", "format": "json", "maxrecords": 50, "sort": "datedesc",
                "startdatetime": since.astimezone(UTC).strftime("%Y%m%d%H%M%S")})
            try:
                articles = resp.json().get("articles", []) if resp.content.strip() else []
                fetched = datetime.now(UTC)
                for a in articles:
                    ts = datetime.strptime(a["seendate"], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
                    out.append(NewsRecord(
                        external_id=a["url"], url=a["url"], title=clean_title(a["title"]), excerpt="",
                        published_at=ts, fetched_at=fetched, source_key=self.key,
                        language=LANG.get(a.get("language", "")), publisher=a.get("domain") or None))
            except (ValueError, KeyError, TypeError) as exc:
                raise SourceError("Unerwartetes Antwortformat") from exc
        return out
