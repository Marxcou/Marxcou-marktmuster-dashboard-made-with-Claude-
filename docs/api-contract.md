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
- **Mehrere Quellen pro Kerze:** `/bars` liefert je Zeitstempel (bei `1d` je Kalendertag) genau eine Kerze, bevorzugt von Alpaca vor Stooq vor Yahoo. `source` nennt die tatsächliche Quelle.
- **Quotes:** US: IEX-Echtzeit (`source.key` `alpaca`, Ausweichquelle `finnhub`), `delay_seconds` 0. XETRA: letzter Tagesschluss aus Stooq (oder Yahoo, wenn eingeschaltet), `delay_seconds` `null`, `source.delay_text` "Handelsende (Tagesdaten)".
- **WS-Event `quote`:** `payload = {instrument_id, symbol, price, change_abs, change_pct, ts_utc, fetched_at, source_key, delay_seconds}`. Höchstens etwa alle 2 Sekunden je Symbol; das Frontend zeigt `ts_utc`/`fetched_at` als "letztes Update".
- **`POST /watchlist`:** stößt im Hintergrund sofort einen Abruf der Historie an; die ersten Kerzen können ein paar Sekunden später erscheinen (leerer Chart mit `empty_reason` bis dahin).
- **`/sources`:** enthält jetzt `alpaca`, `finnhub`, `stooq`, `yahoo`, `openfigi`. Ohne API-Schlüssel steht der Status `disabled` mit `last_error` "API-Schlüssel nicht gesetzt"; `yahoo` (`is_official: false`) ist `disabled` mit "In .env ausgeschaltet (YAHOO_ENABLED=false)", bis es eingeschaltet wird. Muster-Backtest-Läufe nennen in `source.key` `stooq` oder `yahoo`.

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

Zusätzlich zu den bisherigen Feldern: `item_count_24h` (Anzahl in den letzten 24 h gespeicherter Meldungen, nur bei `kind == "news"`, sonst `null`). Neu in der Liste: die News-Quellen `finnhub_news`, `sec_edgar`, `alphavantage_news`, `marketaux`, `gdelt`, optional `ir_feeds` (Investor-Relations-Feeds, aus solange `IR_FEEDS` leer ist), optional `eqs_news` und je ein `rss_<id>` pro RSS-Feed sowie die Stimmungsverfahren `sentiment_lexicon` (`kind: "reference"`) und `claude_sentiment` (`kind: "llm"`). Ohne Schlüssel bzw. ohne Freischaltung steht der Status `disabled` mit `last_error` (Grund).

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

## Phase 3B: Mustererkennung (Muster-Engine)

Erkennung regelbasiert und deterministisch (`backend/app/analysis/`): gleiche Kerzen + gleiche Parameter ergeben dieselben Erkennungen. Jede Erkennung erfüllt die Erklärpflicht (Grundregel 3). Es gibt **keine** Kursziele und keine "Measured Move"-Projektionen; Szenarien nennen nur das Niveau, ab dem ein Muster als bestätigt bzw. ungültig gilt. Die historische Trefferquote kommt aus dem Muster-Backtest (3C); solange er fehlt, ist `backtest.status = "nicht_berechnet"` und alle Zahlen sind `null` (nie geschätzt).

| Methode/Pfad | Auth | Zweck |
|---|---|---|
| GET `/instruments/{id}/patterns?timeframe=1d\|1h&include_invalid=false&start` | ja | `PatternsResponse` (Erkennungen + Unterstützungs-/Widerstandszonen). Standard: nur `in_bildung` und `bestaetigt`; `include_invalid=true` liefert auch `ungueltig`. `start` (ISO) filtert auf Erkennungen mit `end_ts >= start` |
| GET `/patterns/{detection_id}` | ja | Eine `PatternDetection` |
| GET `/patterns/catalog` | ja | Alle Mustertypen mit Beschreibung, Kriterien, Gewichten und dokumentierten Parametern (für "Wie wird das berechnet?") |
| GET `/patterns/counts` | ja | `{counts: {"<instrument_id>": n}, empty_reason}`: aktuelle Muster (`in_bildung` oder in den letzten 20 Kerzen bestätigt) je Instrument der Watchlist, Zeitraster `1d` |
| WS `detection` | Cookie | `payload = {category: "pattern", detection_id, instrument_id, symbol, timeframe, pattern_type, name, status, previous_status, end_ts}` bei neuer Erkennung oder Statuswechsel |

`PatternsResponse`:

```json
{
  "instrument": {"id": 5, "symbol": "SAP", "name": "SAP SE", "isin": "DE0007164600", "exchange": "XETR", "currency": "EUR"},
  "timeframe": "1d",
  "detections": ["PatternDetection …"],
  "zones": ["SRZone …"],
  "data_basis": {"bars_from": "2021-09-29T00:00:00Z", "bars_to": "2026-09-28T00:00:00Z", "bar_count": 1256,
                 "last_fetched_at": "2026-09-28T20:05:00Z", "sources": [{"key": "stooq", "name": "Stooq", "homepage": "…", "terms_url": "…", "delay_text": "…"}]},
  "algo_version": "1.0.0",
  "params_hash": "3f2a9c1e",
  "computed_at": "2026-09-28T20:06:00Z",
  "empty_reason": null
}
```

`empty_reason` erklärt leere Ergebnisse, z. B. "Noch keine Kursdaten gespeichert." oder "Zu wenige Kerzen für die Mustererkennung (mindestens 60, vorhanden 12)." oder "Die Mustererkennung wurde für dieses Instrument noch nicht ausgeführt." Sind Kerzen vorhanden, aber kein Muster erfüllt die Kriterien, ist `detections` leer und `empty_reason` "Aktuell erfüllt kein Muster alle Kriterien."

`PatternDetection`:

```json
{
  "id": 42,
  "instrument_id": 5,
  "timeframe": "1d",
  "pattern_type": "doppelboden",
  "name": "Doppelboden",
  "direction_if_confirmed": "aufwärts",
  "status": "in_bildung",
  "status_label": "In Bildung",
  "status_changed_at": "2026-09-17T00:00:00Z",
  "confirmed_at": null,
  "invalidated_at": null,
  "start_ts": "2026-08-20T00:00:00Z",
  "end_ts": "2026-09-17T00:00:00Z",
  "key_points": [
    {"role": "tief_1", "label": "Tief 1", "ts": "2026-09-03T00:00:00Z", "price": 142.10},
    {"role": "zwischenhoch", "label": "Zwischenhoch", "ts": "2026-09-10T00:00:00Z", "price": 151.40},
    {"role": "tief_2", "label": "Tief 2", "ts": "2026-09-17T00:00:00Z", "price": 141.85}
  ],
  "lines": [
    {"role": "nackenlinie", "label": "Nackenlinie", "start": {"ts": "2026-09-03T00:00:00Z", "price": 151.40}, "end": {"ts": "2026-09-17T00:00:00Z", "price": 151.40}, "extend_right": true}
  ],
  "criteria": [
    {"key": "tief_abweichung", "name": "Abweichung der beiden Tiefs", "rule": "Tiefs weichen höchstens 1,5 % voneinander ab",
     "threshold": 1.5, "actual": 0.18, "unit": "%", "actual_text": "Tief 1: 142,10 am 03.09.2026, Tief 2: 141,85 am 17.09.2026, Abweichung 0,18 %",
     "required": true, "passed": true, "sub_score": 0.88, "weight": 0.35}
  ],
  "confidence": {
    "score": 0.74,
    "method": "Gewichteter Mittelwert der Teilwerte (0 bis 1) aller Kriterien. Ein Teilwert ist 1 beim Idealwert und fällt linear bis 0 an der Grenze des Kriteriums.",
    "breakdown": [{"key": "tief_abweichung", "name": "Abweichung der beiden Tiefs", "weight": 0.35, "sub_score": 0.88, "contribution": 0.308}]
  },
  "confirmation_level": 151.40,
  "invalidation_level": 139.72,
  "scenarios": [
    {"kind": "bestaetigung", "title": "Bestätigung", "trigger_level": 151.40,
     "trigger_rule": "Schlusskurs über der Nackenlinie bei 151,40",
     "description": "Schließt der Kurs über 151,40, gilt der Doppelboden als bestätigt. Historisch: siehe backtest.",
     "historical": null},
    {"kind": "scheitern", "title": "Scheitern", "trigger_level": 139.72,
     "trigger_rule": "Schlusskurs unter 139,72 (tieferes Tief minus 1,5 %)",
     "description": "Schließt der Kurs unter 139,72, bevor die Nackenlinie überschritten wird, gilt das Muster als ungültig.",
     "historical": null}
  ],
  "backtest": {
    "status": "nicht_berechnet", "run_id": null, "hit_rate": null, "sample_size": null, "ci_low": null, "ci_high": null,
    "base_rate": null, "not_better_than_random": null, "horizon_bars": null, "min_move_pct": null,
    "universe": null, "date_range": null, "computed_at": null, "survivorship_note": null, "verdict_text": null,
    "note": "Die historische Trefferquote für dieses Muster wurde noch nicht berechnet."
  },
  "explanation": "Doppelboden zwischen 20.08.2026 und 17.09.2026: …",
  "data_basis": {"bars_from": "…", "bars_to": "…", "bar_count": 1256, "last_fetched_at": "…", "sources": ["SourceRef …"]},
  "params": {"max_tief_abweichung_pct": 1.5, "…": "…"},
  "algo_version": "1.0.0",
  "params_hash": "3f2a9c1e",
  "detected_at": "2026-09-17T20:06:00Z"
}
```

- **`pattern_type`** (Name): `kopf_schulter` (Kopf-Schulter-Formation), `kopf_schulter_invers` (Inverse Kopf-Schulter-Formation), `doppelhoch` (Doppelhoch), `doppelboden` (Doppelboden), `dreieck_aufsteigend` (Aufsteigendes Dreieck), `dreieck_absteigend` (Absteigendes Dreieck), `dreieck_symmetrisch` (Symmetrisches Dreieck), `flagge_aufwaerts`/`flagge_abwaerts` (Flagge nach Anstieg/Rückgang), `wimpel_aufwaerts`/`wimpel_abwaerts` (Wimpel nach Anstieg/Rückgang), `keil_steigend` (Steigender Keil), `keil_fallend` (Fallender Keil).
- **`direction_if_confirmed`**: `aufwärts` \| `abwärts` \| `offen` (symmetrisches Dreieck: Richtung ergibt sich erst aus dem Ausbruch). Beschreibend, keine Handlungsaufforderung.
- **`status`**: `in_bildung` (weder Bestätigungs- noch Ungültigkeitsniveau per Schlusskurs überschritten), `bestaetigt`, `ungueltig`. Es zählt das zuerst eingetretene Ereignis; `confirmed_at`/`invalidated_at` nennen die Kerze. Nach einer Bestätigung bleibt der Status `bestaetigt`, auch wenn der Kurs später zurückfällt (`invalidated_at` wird dann trotzdem gesetzt).
- **`key_points[].role`** je Muster: z. B. `linke_schulter`, `kopf`, `rechte_schulter`, `nacken_1`, `nacken_2`, `hoch_1`, `hoch_2`, `tief_1`, `tief_2`, `zwischenhoch`, `zwischentief`, `fahnenstange_start`, `fahnenstange_ende`, `beruehrung_oben_n`, `beruehrung_unten_n`. `label` ist der deutsche Anzeigetext.
- **`lines`**: Linien zum Einzeichnen (Nackenlinie, obere/untere Begrenzung). `extend_right: true` heißt: bis zur letzten Kerze verlängern (dort liegt das aktuelle Auslöseniveau).
- **`criteria`**: alle geprüften Kriterien mit tatsächlichem Wert. `required: true` sind Pflichtkriterien (eine Erkennung existiert nur, wenn alle erfüllt sind); `required: false` sind Qualitätskriterien (z. B. Volumenverlauf), die nur den Konfidenz-Score beeinflussen und auch `passed: false` sein können. `threshold`/`actual` sind Zahlen in `unit` (`%`, `Kerzen`, `Preis`, `Faktor`, `Anzahl`), `actual_text` ist fertig formatiert (de-DE).
- **`confidence.score`** 0..1 (UI zeigt Prozent). `breakdown[].contribution = weight × sub_score`, Summe = `score`. Die Gewichte je Muster stehen auch in `/patterns/catalog`.
- **`scenarios[].kind`**: `bestaetigung` \| `scheitern`; beim symmetrischen Dreieck `ausbruch_oben` \| `ausbruch_unten`. Immer mindestens zwei. `trigger_level` ist bei schrägen Linien der Wert der Linie an der letzten Kerze.
- **`scenarios[].historical`** und **`backtest`**: kommen aus der Tabelle `backtest_runs` (Workstream 3C schreibt sie, `kind = "pattern"`, `subject = pattern_type`, gleiche `timeframe` und `algo_version`; es gilt der neueste Lauf). Mit Lauf: `status = "berechnet"`, `hit_rate`/`base_rate`/`ci_low`/`ci_high` 0..1, `sample_size` Anzahl Fälle, `not_better_than_random = true`, wenn das 95-%-Intervall die Basisrate überdeckt; `verdict_text` z. B. "Historisch nicht besser als Zufall"; `survivorship_note` nennt die Verzerrung durch heutige Indexmitglieder; `historical` = `{share, sample_size, text}` aus `metrics.scenarios[kind]`. Ohne Lauf: wie oben, alles `null`.
- **Muster-Backtest (3C, umgesetzt):** `python -m app.backtest_job` schreibt je Mustertyp einen Lauf (`timeframe = "1d"`; für `1h` gibt es keinen, dort bleibt `nicht_berechnet`). `not_better_than_random` ist `true`, sobald die untere Grenze des 95-%-Intervalls nicht über der Basisrate liegt (Intervall überdeckt sie **oder liegt ganz darunter**). Zusätzlich (additiv) im `backtest`-Block: `mean_return_pct`, `median_return_pct` (Veränderung nach `horizon_bars` Kerzen in Musterrichtung, in %), `base_mean_return_pct` (dasselbe über alle Handelstage), `method` (Beschreibung des Verfahrens), `source` (`{key, name, homepage, terms_url, delay_text, fetched_from, fetched_to}`). Ohne Fälle: `status = "berechnet"`, `sample_size = 0`, alle Quoten `null`, `note` nennt den Grund. `metrics` des Laufs enthält außerdem `hits`, `cases_open`, `cases_excluded`, `detections_seen`, `symbols_used`, `symbols_missing`, `scenarios`.
- **`explanation`**: deterministischer deutscher Erklärtext aus den berechneten Werten (kein KI-Text).
- **Ergänzt bei der Umsetzung (additiv):** `status_reason` (Begründung des Status, z. B. "Keine Bestätigung bis zum Fristende am …"), `breakout_direction` (`aufwärts`/`abwärts` beim symmetrischen Dreieck nach Ausbruch, sonst `null`), `formed_at` (letzte Kerze, deren Daten in die Erkennung eingehen; erst ab hier war das Muster in Echtzeit erkennbar, wichtig für den Backtest ohne Vorgriff), `is_demo`. `status_changed_at` ist bei `in_bildung` gleich `formed_at`. `trigger_level` schräger Linien ist der Linienwert an der Kerze des Statuswechsels bzw. (in Bildung) an der letzten Kerze. Ohne Bestätigung bis zur Frist (Musterbreite, mindestens 10, höchstens 60 Kerzen; bei Flaggen 10 Kerzen) oder beim Erreichen der Dreiecksspitze wird ein Muster `ungueltig`.
- **Fristen und Niveaus je Muster:** Doppel-Muster und Kopf-Schulter: Bestätigung per Schlusskurs jenseits der Nackenlinie, ungültig jenseits des äußeren Extrempunkts (Doppel) bzw. der rechten Schulter (Kopf-Schulter) plus 1,5 %. Dreiecke/Keile: jeweilige Begrenzungslinie (verlängert). Flaggen/Wimpel: Kanal-Linie in Richtung der Fahnenstange; ungültig jenseits des Extrems der Konsolidierung.
- **Für 3C (Backtest):** Die Engine ist `app.analysis.engine.detect(bars, timeframe, params)` (reines numpy, ohne DB). `Detection.formed_idx`, `confirmed_idx`, `invalidated_idx` sind Kerzenindizes; Wendepunkte tragen `confirmed_idx`, sodass ein Lauf auf einer abgeschnittenen Reihe dieselben Wendepunkte liefert (Test `test_pivots_are_confirmed_later_and_without_lookahead`).

`SRZone` (Unterstützungs- und Widerstandszonen aus Pivot-Häufungen):

```json
{
  "id": 7,
  "kind": "unterstuetzung",
  "kind_label": "Unterstützungszone",
  "lower": 139.80, "upper": 142.30, "center": 141.05,
  "touch_count": 4,
  "touches": [{"ts": "2026-03-12T00:00:00Z", "price": 140.10, "role": "tief"}],
  "first_touch": "2026-03-12T00:00:00Z", "last_touch": "2026-09-17T00:00:00Z",
  "criteria": ["Criterion …"],
  "confidence": {"score": 0.66, "method": "…", "breakdown": ["…"]},
  "explanation": "Zone zwischen 139,80 und 142,30: 4 Wendepunkte seit 12.03.2026 …"
}
```

Zusätzlich je Zone: `sources` (Kursquellen der verwendeten Kerzen), `fetched_at`, `is_demo`. `kind` ist relativ zum letzten Schlusskurs: Zone unterhalb = `unterstuetzung`, oberhalb = `widerstand`, Kurs innerhalb = `im_bereich` ("Kurs innerhalb der Zone").

`/patterns/catalog` liefert `{algo_version, params_hash, confidence_method, items: [...]}`; ein Eintrag: `{pattern_type, name, direction_if_confirmed, description, criteria: [{key, name, rule, required, weight}], params: [{key, value, unit, description}], algo_version}`.

## Phase 4A: Prognosen, Szenarien, Prognose-Backtest (Backend)

Prognosen gibt es nur als Korridor (Grundregel 4): je Schritt die Quantile 2,5/10/25/50/75/90/97,5 %, daraus die Bänder 50 % (25–75), 80 % (10–90) und 95 % (2,5–97,5). Es gibt **keinen** Endpunkt für eine einzelne Linie; der Median (`"50"`) ist nur die Mitte der Bänder und wird nicht allein gezeichnet. Alles ist aus gespeicherten, abgeschlossenen Tageskerzen berechnet (deterministisch, fester Zufalls-Seed je Datenstand). Fehlermaße stammen ausschließlich aus einem Backtest auf den gespeicherten Kerzen; ohne Lauf ist `backtest.status = "nicht_berechnet"` und alle Zahlen sind `null` (nie geschätzt).

| Methode/Pfad | Auth | Zweck |
|---|---|---|
| GET `/instruments/{id}/forecast?timeframe=1d&horizon=20` | ja | `ForecastResponse`. `horizon` 1 bis 20 Kerzen (Standard 20) kürzt nur `steps`. Nur `timeframe=1d`; sonst 200 mit `empty_reason`. 404 nur bei unbekanntem Instrument |
| GET `/forecasts/methods` | ja | Beschreibung aller Methoden: `{algo_version, items: [{key, name, description, assumptions[], limitations[], params}]}` |

`ForecastResponse`:

```json
{
  "instrument_id": 5, "timeframe": "1d",
  "method": {"key": "monte_carlo_block_bootstrap", "name": "Monte-Carlo-Simulation (Block-Bootstrap)",
             "description": "…", "assumptions": ["…"], "limitations": ["…"],
             "params": {"lookback_bars": 750, "block_length": 10, "paths": 4000, "seed": 1234567}},
  "horizon_bars": 20,
  "based_on_until": "2026-09-28T00:00:00Z", "last_close": 151.2, "currency": "EUR",
  "generated_at": "2026-09-28T20:10:00Z", "algo_version": "forecast-1", "params_hash": "a1b2c3d4", "is_demo": false,
  "steps": [{"step": 1, "ts": "2026-09-29T00:00:00Z",
             "quantiles": {"2.5": 146.0, "10": 148.1, "25": 149.8, "50": 151.2, "75": 152.7, "90": 154.3, "97.5": 156.5}}],
  "bands": [{"level": 0.5, "lower": "25", "upper": "75"}, {"level": 0.8, "lower": "10", "upper": "90"},
            {"level": 0.95, "lower": "2.5", "upper": "97.5"}],
  "backtest": "ForecastBacktest …",
  "comparison": [{"method_key": "arima_1_1_0", "name": "ARIMA(1,1,0) auf Log-Kursen", "description": "…",
                  "steps": ["… wie oben"], "backtest": "ForecastBacktest …", "metrics": ["… = backtest.metrics"]}],
  "pattern_scenarios": ["PatternScenarioLink …"],
  "data_basis": {"bars_from": "…", "bars_to": "…", "bar_count": 1256, "last_fetched_at": "…", "sources": ["SourceRef …"]},
  "note": "Statistische Szenarien aus historischen Schwankungen, keine Vorhersage und keine Anlageberatung.",
  "empty_reason": null
}
```

- **`steps[].ts`**: Handelstage vereinfacht als Werktage (Mo–Fr) nach `based_on_until`; Feiertage sind nicht berücksichtigt (steht in `method.limitations`).
- **`method`** ist die Hauptmethode (Korridor im Chart). **`comparison`** enthält die Vergleichsmethode ARIMA(1,1,0) mit demselben Aufbau; Frontend kann sie im Methoden-Panel zeigen.
- **`empty_reason`** z. B. "Noch keine Kursdaten gespeichert.", "Zu wenige Kerzen für eine Prognose (mindestens 250, vorhanden 80).", "Die Prognose wurde für dieses Instrument noch nicht berechnet.", "Prognosen gibt es derzeit nur für Tageskerzen." Dann ist `steps` leer und `method` trotzdem gesetzt (Beschreibung bleibt einsehbar).

`ForecastBacktest` (rollierender Ursprung: an vielen vergangenen Tagen wird nur mit den bis dahin bekannten Kerzen prognostiziert und mit dem später tatsächlich eingetretenen Schlusskurs verglichen):

```json
{
  "status": "berechnet", "run_id": 17, "sample_size": 142, "horizon_bars": 20,
  "date_range": "2023-10-02 – 2026-08-31", "universe": "SAP (XETR), eigene Historie", "computed_at": "…", "is_demo": false,
  "coverage": [{"nominal": 0.5, "observed": 0.47}, {"nominal": 0.8, "observed": 0.76}, {"nominal": 0.95, "observed": 0.93}],
  "metrics": [
    {"key": "median_abs_error", "name": "Mittlerer absoluter Fehler des Medians", "model": 4.1, "naive": 4.3, "unit": "%"},
    {"key": "pinball_loss", "name": "Pinball-Verlust (Mittel über alle Quantile)", "model": 1.2, "naive": 2.1, "unit": "%"}
  ],
  "skill": 0.05, "dm_p_value": 0.21, "better_than_naive": false,
  "verdict_text": "Beim Median nicht nachweisbar besser als die naive Referenz \"Kurs bleibt gleich\" (p = 0,21).",
  "by_horizon": [{"horizon_bars": 5, "sample_size": 142, "coverage": ["…"], "metrics": ["…"], "skill": 0.01,
                  "dm_p_value": 0.4, "better_than_naive": false}],
  "method_note": "…", "note": null
}
```

- Fehler in Prozent des Kurses am Prognoseursprung. `naive` = Referenz "Kurs bleibt gleich" (alle Quantile = letzter Schlusskurs). `skill = 1 − model/naive` beim Median-Fehler.
- `better_than_naive`: `true` nur, wenn der Median-Fehler kleiner ist **und** der Diebold-Mariano-Test (einseitig, Newey-West-Varianz) p < 0,05 ergibt; sonst `false` und `verdict_text` sagt es offen. `null` bei zu kleiner Stichprobe (< 30 Ursprünge).
- Hauptwerte gelten für `horizon_bars` (20); `by_horizon` für 5, 10, 20.
- Ohne Lauf: `{"status": "nicht_berechnet", "run_id": null, "sample_size": null, …, "coverage": [], "metrics": [], "better_than_naive": null, "note": "Die Prognosegüte wurde für dieses Instrument noch nicht berechnet."}`.
- Gespeichert in `backtest_runs` mit `kind = "forecast"`, `subject` = Methodenschlüssel, `universe` = Instrument; die Prognose verweist per `backtest_run_id` darauf.

`PatternScenarioLink` (Verknüpfung mit den aktuellen Mustern aus 3B, nur `in_bildung`):

```json
{
  "detection_id": 42, "pattern_type": "doppelboden", "name": "Doppelboden", "status": "in_bildung",
  "scenarios": [
    {"kind": "bestaetigung", "title": "Bestätigung", "trigger_level": 151.40,
     "model_probability": 0.31, "model_probability_text": "In 31 % der simulierten Pfade schließt der Kurs innerhalb von 20 Handelstagen zuerst über 151,40.",
     "historical": {"share": 0.58, "sample_size": 214, "text": "…"}},
    {"kind": "scheitern", "title": "Scheitern", "trigger_level": 139.72, "model_probability": 0.12, "model_probability_text": "…", "historical": null}
  ],
  "neither_probability": 0.57,
  "note": "Die Simulation kennt das Muster nicht; sie zeigt nur, wie oft die Niveaus bei historischer Schwankung zuerst erreicht würden. Die historische Quote stammt aus dem Muster-Backtest."
}
```

`historical` ist dasselbe Objekt wie `scenarios[].historical` in `PatternDetection` (aus dem Muster-Backtest, sonst `null`).
