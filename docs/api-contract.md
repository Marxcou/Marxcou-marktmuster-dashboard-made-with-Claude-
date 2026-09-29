# API-Vertrag (Stand Phase 1B)

Alle Pfade unter `/api`, JSON. Login per Cookie `session` (httpOnly). Unsichere Methoden (POST/DELETE/...) brauchen den Header `X-CSRF-Token` mit dem Wert aus `/api/auth/login` bzw. `/api/auth/me`. Zeitstempel sind ISO-8601 in UTC; das Frontend formatiert nach Europe/Berlin.

Jeder Kurs/jede Kerze trägt `source` (`key`, `name`, `homepage`, `terms_url`, `delay_text`) und `fetched_at` (Grundregel 2). Fehlende Daten werden über `empty_reason` erklärt, nie durch Platzhalter ersetzt.

| Methode/Pfad | Auth | Zweck |
|---|---|---|
| GET `/health` | nein | Liveness |
| GET `/meta` | nein | `demo_mode`, `timezone`, `disclaimer` |
| POST `/auth/login` `{email,password}` | nein | Setzt Cookie, liefert `{user, csrf_token}` |
| GET `/auth/me` | ja | `{user, csrf_token}` |
| POST `/auth/logout` | ja | 204 |
| GET/POST `/users` | Admin | Nutzer auflisten/einladen (keine offene Registrierung) |
| GET `/instruments/search?q=` | ja | Suche nach Ticker, Name, ISIN in lokal gespeicherten Instrumenten plus OpenFIGI (Treffer werden gespeichert, max. 25). Fällt OpenFIGI aus, kommen die lokalen Treffer. Antwortform unverändert |
| GET `/instruments/{id}` | ja | Instrument + letzter Kurs (`quote` oder `null`) |
| GET `/instruments/{id}/bars?timeframe=1m\|5m\|1h\|1d&start&end&limit` | ja | `{instrument, timeframe, bars[], empty_reason}` |
| GET `/watchlist` · POST `/watchlist {instrument_id}` · DELETE `/watchlist/{instrument_id}` | ja | Watchlist des Nutzers, Instrumente mit letztem Kurs |
| GET `/sources` | ja | Quellen mit Metadaten und Status (aus Adapter-Metadaten + Health) |
| WS `/ws` | Cookie | Events `{id, type: quote\|news\|detection\|source_status, payload, created_at}` |

## Ergänzungen durch 1B (keine Änderung der Antwortformen)

- **`empty_reason` bei `/bars`:** für XETRA-Instrumente und `timeframe` ≠ `1d` lautet er "Keine Intraday-Daten für XETRA im kostenlosen Tarif. Verfügbar sind Tagesdaten (Handelsende)." (`bars` ist dann leer). Sonst wie bisher, wenn noch keine Daten gespeichert sind.
- **Mehrere Quellen pro Kerze:** `/bars` liefert je Zeitstempel (bei `1d` je Kalendertag) genau eine Kerze, bevorzugt von Alpaca vor Stooq. `source` nennt die tatsächliche Quelle.
- **Quotes:** US: IEX-Echtzeit (`source.key` `alpaca`, Ausweichquelle `finnhub`), `delay_seconds` 0. XETRA: letzter Tagesschluss aus Stooq, `delay_seconds` `null`, `source.delay_text` "Handelsende (Tagesdaten)".
- **WS-Event `quote`:** `payload = {instrument_id, symbol, price, change_abs, change_pct, ts_utc, fetched_at, source_key, delay_seconds}`. Höchstens etwa alle 2 Sekunden je Symbol; das Frontend zeigt `ts_utc`/`fetched_at` als "letztes Update".
- **`POST /watchlist`:** stößt im Hintergrund sofort einen Abruf der Historie an; die ersten Kerzen können ein paar Sekunden später erscheinen (leerer Chart mit `empty_reason` bis dahin).
- **`/sources`:** enthält jetzt `alpaca`, `finnhub`, `stooq`, `openfigi`. Ohne API-Schlüssel steht der Status `disabled` mit `last_error` "API-Schlüssel nicht gesetzt".

## Schnittstellen für die Folge-Workstreams

- **1B (Kursdaten):** implementiert `PriceAdapter` (`backend/app/adapters/base.py`), registriert ihn in `load_builtin_adapters()` (`adapters/registry.py`), hängt Jobs in `JOBS` (`worker.py`) ein, schreibt `Instrument`, `PriceBar`, `Quote` (immer mit `source_id` und `fetched_at`) und ruft `events.publish(db, "quote", {...})` auf. Liefert die Anbieter-Suche über `PriceAdapter.search_instruments` und erweitert `/instruments/search`.
- **1C (Frontend):** ersetzt die Platzhalter in `frontend/src/App.tsx`, nutzt `frontend/src/lib/api.ts` (Typen spiegeln diesen Vertrag) und `lib/format.ts` (de-DE). Layout inkl. Hinweis und Demo-Banner bleibt in `components/Layout.tsx`.
- **Neue Tabellen** kommen je Workstream per eigener Alembic-Migration (`cd backend && alembic revision --autogenerate`).

## Phase 2: News und Quellen (Backend 2A/2B/2C)

Alle Antworten enthalten `source`-Objekte (Grundregel 2). Stimmung und Cluster sind berechnet; die Originalmeldungen (`items`) bleiben einzeln mit Quelle, Link, Veröffentlichungs- und Abrufzeit sichtbar. Es werden nur Überschrift, kurzer Auszug (max. 300 Zeichen) und Link gespeichert, nie Volltexte.

| Methode/Pfad | Auth | Zweck |
|---|---|---|
| GET `/news?instrument_id&source&sentiment&since&until&limit&cursor` | ja | `{items: NewsCluster[], total, next_cursor, empty_reason}`. `source` = Quellen-`key` (Cluster mit mindestens einer Meldung dieser Quelle). `sentiment` = `positiv\|neutral\|negativ`. Sortierung: `first_published_at` absteigend. `limit` max. 100 (Standard 25). `cursor` ist undurchsichtig (aus `next_cursor`) |
| GET `/instruments/{id}/news?since&until&limit&cursor` | ja | Wie `/news` für ein Instrument (Chart-Marker: Zeitpunkt = `first_published_at`) |
| GET `/news/counts?since` | ja | `{counts: {"<instrument_id>": n}, empty_reason}`: Anzahl Cluster je Instrument der Watchlist des Nutzers seit `since` (Standard: 24 h) |
| GET `/news/sentiment-status` | ja | Welches Verfahren aktuell aktiv ist: `{active_method: "claude"\|"lexicon", claude_configured, budget_usd, spent_usd, month, fallback_reason}`. `fallback_reason` ist z. B. "Kein API-Schlüssel gesetzt" oder "Monatslimit erreicht", sonst `null`. Zusätzlich `claude_mode` (`batch`\|`direct`) und `pending_batches` (Anzahl offener Claude-Batches; im Modus `batch` steht bis zum Ergebnis die Lexikon-Stimmung) |
| WS `news` | Cookie | `payload = {cluster_id, canonical_title, first_published_at, item_count, instrument_ids, is_new}` bei neuem Cluster bzw. wenn eine weitere Quelle zu einem Cluster kommt |

`NewsCluster`:

```json
{
  "id": 1,
  "canonical_title": "…",
  "first_published_at": "2026-09-28T12:00:00Z",
  "last_published_at": "2026-09-28T12:20:00Z",
  "item_count": 3,
  "instruments": [{"id": 5, "symbol": "AAPL", "match_method": "provider_tag"}],
  "sentiment": {
    "label": "positiv", "score": 0.5, "method": "lexicon", "model_name": "Finanz-Lexikon (regelbasiert)",
    "model_version": "1", "rationale": "…", "evidence": ["Rekordgewinn"], "created_at": "…"
  },
  "items": [{"id": 1, "title": "…", "excerpt": "…", "url": "https://…", "published_at": "…",
             "fetched_at": "…", "language": "en", "publisher": "Reuters", "source": {"key": "finnhub_news", "name": "Finnhub", "homepage": "…", "terms_url": "…", "delay_text": "…"}}]
}
```

- `items[].publisher`: ursprünglicher Verlag bzw. Domain, wenn der Anbieter Meldungen weiterreicht (z. B. Finnhub, Marketaux, GDELT), sonst `null`.
- `instruments[].match_method`: `provider_tag` (Anbieter liefert das Symbol), `isin`, `ticker` (Cashtag oder Tickersymbol im Titel), `name` (Firmenname im Titel/Auszug).
- `sentiment` ist `null`, solange noch nicht berechnet. `method` ist `lexicon` oder `claude`; `model_name` nennt das verwendete Verfahren bzw. Modell (Grundregel: Modell angeben). `evidence` sind wörtliche Zitate aus Überschrift/Auszug (bei `claude` vom Backend gegen den Text geprüft).
- Meldungen mit KI-Stimmung sind im UI als "KI-generiert" zu kennzeichnen (`method == "claude"`).
- `empty_reason` erklärt leere Listen (z. B. "Noch keine Meldungen abgerufen. Quellen ohne API-Schlüssel sind deaktiviert, siehe Seite Quellen.").
- Der Filter `instrument_id` nutzt nur belegte Zuordnungen; Meldungen ohne Zuordnung erscheinen nur in `/news` ohne Filter.

### `/sources` (Erweiterung, additiv)

Zusätzlich zu den bisherigen Feldern: `item_count_24h` (Anzahl in den letzten 24 h gespeicherter Meldungen, nur bei `kind == "news"`, sonst `null`). Neu in der Liste: die News-Quellen `finnhub_news`, `sec_edgar`, `alphavantage_news`, `marketaux`, `gdelt`, optional `eqs_news` und je ein `rss_<id>` pro RSS-Feed sowie die Stimmungsverfahren `sentiment_lexicon` (`kind: "reference"`) und `claude_sentiment` (`kind: "llm"`). Ohne Schlüssel bzw. ohne Freischaltung steht der Status `disabled` mit `last_error` (Grund).
