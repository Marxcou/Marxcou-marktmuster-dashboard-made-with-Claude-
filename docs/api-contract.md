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

## Phase 3A: Indikatoren, Indikator-Ereignisse, News↔Kurs (Backend)

Alle Werte sind aus gespeicherten Kerzen berechnet (reines Python, deterministisch, versionierte Parameter). Jede Antwort nennt die Kursquellen der Eingangskerzen (`sources`, `fetched_at`) und `algo_version` (Grundregel 2). Die Serien enthalten auch die laufende Kerze (wie `/bars`); Ereignisse und Bewegungen werten nur abgeschlossene Kerzen aus. Es gibt keine Kauf-/Verkaufssprache; Richtungen heißen `up`/`down` und beschreiben nur die Lage der Werte.

### Indikator-Serien für den Chart

`GET /instruments/{id}/indicators?timeframe=1d&start&end&limit&sma=20,50&ema=12,26&rsi=14&macd=12,26,9&bb=20,2`

- Nur angeforderte Indikatoren werden berechnet und geliefert; jeder Parameter darf fehlen. `sma`/`ema`: kommaseparierte Perioden (max. 5 je Typ, 2 bis 500). `rsi`: Periode. `macd`: `schnell,langsam,signal`. `bb`: `periode,faktor` (Standardabweichungen, Faktor 0,5 bis 5).
- `timeframe`, `start`, `end`, `limit` wie bei `/bars` (Standard-`limit` 2000, max. 10000). Das Backend lädt zusätzlich 400 Kerzen Vorlauf zur Einschwingung (nicht in der Antwort). EMA/RSI starten mit dem SMA der ersten `n` Werte bzw. dem Wilder-Mittel der ersten `n` Änderungen; Werte vor dem ersten gültigen Punkt sind `null`.
- Die Arrays sind index-gleich zu `timestamps` (UTC, gleiche Kerzen wie `/bars` mit demselben `limit`/Fenster; bei mehreren Quellen je Kerze gilt dieselbe Priorität wie dort).

```json
{
  "instrument_id": 5, "timeframe": "1d", "algo_version": "indicators-1",
  "timestamps": ["2026-09-25T00:00:00Z", "…"],
  "indicators": [
    {"key": "sma_20", "type": "sma", "params": {"period": 20}, "label": "SMA (20)", "panel": "price",
     "formula": "Arithmetisches Mittel der letzten 20 Schlusskurse", "lines": {"value": [null, 141.2, "…"]}},
    {"key": "rsi_14", "type": "rsi", "params": {"period": 14}, "label": "RSI (14)", "panel": "own",
     "range": [0, 100], "reference_lines": [30, 70], "formula": "…", "lines": {"value": ["…"]}},
    {"key": "macd_12_26_9", "type": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}, "panel": "own",
     "lines": {"macd": ["…"], "signal": ["…"], "histogram": ["…"]}},
    {"key": "bb_20_2", "type": "bollinger", "params": {"period": 20, "factor": 2.0}, "panel": "price",
     "lines": {"middle": ["…"], "upper": ["…"], "lower": ["…"]}}
  ],
  "sources": [{"key": "alpaca", "name": "…", "homepage": "…", "terms_url": "…", "delay_text": "…"}],
  "bars_fetched_at": "2026-09-29T11:00:00Z", "computed_at": "2026-09-29T11:00:05Z",
  "empty_reason": null
}
```

`panel`: `price` (im Kursfenster) oder `own` (eigenes Teilfenster). `formula` ist die Klartext-Formel für die Anzeige. Fehlen Kerzen, ist `indicators` leer und `empty_reason` erklärt es; sind zu wenige Kerzen für eine Periode da, ist die Serie komplett `null`.

### Indikator-Ereignisse

`GET /instruments/{id}/indicator-events?timeframe&type&since&until&limit&cursor` → `{events: IndicatorEvent[], next_cursor, empty_reason}`, Sortierung `ts` absteigend, `limit` max. 200 (Standard 50).

`type`: `golden_cross`, `death_cross`, `rsi_divergence`, `bb_breakout`, `volume_spike`. `direction`: `up`, `down` oder `null` (`volume_spike`).
- `golden_cross`/`death_cross`: SMA(50) kreuzt SMA(200) von unten (`up`) bzw. oben (`down`).
- `rsi_divergence`: `up` = Kurs macht ein tieferes Tief, RSI ein höheres Tief; `down` = Kurs höheres Hoch, RSI tieferes Hoch.
- `bb_breakout`: Schlusskurs liegt erstmals außerhalb des oberen (`up`) bzw. unteren (`down`) Bollinger-Bands (20, 2).
- `volume_spike`: Volumen liegt deutlich über dem Mittel der 20 Vorkerzen.

```json
{
  "id": 12, "instrument_id": 5, "timeframe": "1d", "type": "rsi_divergence", "direction": "up",
  "ts": "2026-09-17T00:00:00Z", "start_ts": "2026-09-03T00:00:00Z", "end_ts": "2026-09-17T00:00:00Z",
  "confirmed_at": "2026-09-24T00:00:00Z",
  "title": "RSI-Divergenz (Kurs tiefer, RSI höher)",
  "summary": "Der Kurs bildete am 17.09. ein tieferes Tief (141,85 € statt 142,10 €), der RSI(14) dagegen ein höheres Tief (34,2 statt 29,8).",
  "criteria": [{"name": "Tieferes Kurstief", "rule": "Tief 2 < Tief 1", "required": "< 142,10", "actual": "141,85", "passed": true}],
  "values": {"pivot1": {"ts": "…", "price": 142.10, "rsi": 29.8}, "pivot2": {"ts": "…", "price": 141.85, "rsi": 34.2}},
  "params": {"rsi_period": 14, "pivot_window": 5, "min_bars_apart": 5, "max_bars_apart": 60, "min_rsi_diff": 2.0},
  "algo_version": "indicator-events-1",
  "historical_stats": null,
  "historical_stats_reason": "Für Indikator-Ereignisse wird noch keine historische Trefferquote berechnet.",
  "sources": [{"key": "stooq", "…": "…"}], "bars_fetched_at": "…", "detected_at": "…"
}
```

- `ts` ist der Zeitpunkt, an dem das Ereignis im Chart markiert wird (Kerze, deren Schluss die Bedingung erfüllt; bei `rsi_divergence` das zweite Extrem). `confirmed_at` ist die Kerze, ab der es erkennbar war (bei Divergenzen: `pivot_window` Kerzen später; sonst gleich `ts`). Nur abgeschlossene Kerzen zählen; die laufende Kerze wird nie ausgewertet.
- `criteria[]`: jede erfüllte Bedingung mit tatsächlichen Werten (`required`/`actual` sind fertig formatierte Texte in de-DE; die Zahlen stehen zusätzlich unformatiert in `values`).
- `historical_stats` ist bis zum Muster-Backtest (3C) `null`; die UI zeigt dann `historical_stats_reason` statt einer Trefferquote (keine erfundenen Zahlen).

### Auffällige Kursbewegungen und zeitlich passende Meldungen

`GET /instruments/{id}/move-links?timeframe&since&until&limit` → `{moves: NotableMove[], note, empty_reason}`.

Eine Bewegung ist auffällig, wenn die Rendite einer Kerze (Schluss zu Vorschluss) mehr als 3 Standardabweichungen der Renditen der 60 Vorkerzen entfernt ist (`return_z`) oder das Volumen mehr als 3 (`volume_z`). Die Meldungen sind Cluster desselben Instruments, deren erste Veröffentlichung im Zeitfenster liegt (`window_before_minutes`/`window_after_minutes` um `move_start`/`move_end`). `note` ist immer: "Zeitlich zusammenfallend, keine Aussage über Ursache." Gibt es keine Meldung im Fenster, ist `news` leer (wird so angezeigt).

```json
{
  "id": 3, "instrument_id": 5, "timeframe": "1d", "move_start": "2026-09-24T00:00:00Z", "move_end": "2026-09-25T00:00:00Z",
  "return_pct": -4.1, "return_z": -3.6, "volume_z": 2.1, "reasons": ["return_z"],
  "params": {"lookback_bars": 60, "z_threshold": 3.0, "window_before_minutes": 1440, "window_after_minutes": 360},
  "algo_version": "move-links-1", "sources": [{"key": "stooq", "…": "…"}], "bars_fetched_at": "…", "detected_at": "…",
  "news": [{"cluster_id": 7, "canonical_title": "…", "first_published_at": "…", "time_offset_minutes": -95, "item_count": 3,
            "sources": [{"key": "finnhub_news", "…": "…"}]}]
}
```

`time_offset_minutes` = `first_published_at − move_start` (negativ: vor Beginn der Kerze). Die Meldung selbst (alle Quellen) kommt über `/instruments/{id}/news` bzw. `/news` (`cluster_id`).

### WebSocket

Neues Ereignis vom Typ `detection` (bestehender Typ) mit `payload = {category: "indicator_event", event_id, instrument_id, timeframe, type, direction, ts}`. Muster-Erkennungen (3B) nutzen denselben Typ mit `category: "pattern"`; das Frontend unterscheidet nach `category`.
