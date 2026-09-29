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
| GET `/news/sentiment-status` | ja | Welches Verfahren aktuell aktiv ist: `{active_method: "claude"\|"lexicon", claude_configured, budget_usd, spent_usd, month, fallback_reason}`. `fallback_reason` ist z. B. "Kein API-Schlüssel gesetzt" oder "Monatslimit erreicht", sonst `null` |
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

## Phase 3B: Mustererkennung (Muster-Engine)

Erkennung regelbasiert und deterministisch (`backend/app/analysis/`): gleiche Kerzen + gleiche Parameter ergeben dieselben Erkennungen. Jede Erkennung erfüllt die Erklärpflicht (Grundregel 3). Es gibt **keine** Kursziele und keine "Measured Move"-Projektionen; Szenarien nennen nur das Niveau, ab dem ein Muster als bestätigt bzw. ungültig gilt. Die historische Trefferquote kommt aus dem Muster-Backtest (3C); solange er fehlt, ist `backtest.status = "nicht_berechnet"` und alle Zahlen sind `null` (nie geschätzt).

| Methode/Pfad | Auth | Zweck |
|---|---|---|
| GET `/instruments/{id}/patterns?timeframe=1d\|1h&include_invalid=false&start` | ja | `PatternsResponse` (Erkennungen + Unterstützungs-/Widerstandszonen). Standard: nur `in_bildung` und `bestaetigt`; `include_invalid=true` liefert auch `ungueltig`. `start` (ISO) filtert auf Erkennungen mit `end_ts >= start` |
| GET `/patterns/{detection_id}` | ja | Eine `PatternDetection` |
| GET `/patterns/catalog` | ja | Alle Mustertypen mit Beschreibung, Kriterien, Gewichten und dokumentierten Parametern (für "Wie wird das berechnet?") |
| GET `/patterns/counts` | ja | `{counts: {"<instrument_id>": n}, empty_reason}`: aktuelle Muster (`in_bildung` oder in den letzten 20 Kerzen bestätigt) je Instrument der Watchlist, Zeitraster `1d` |
| WS `detection` | Cookie | `payload = {detection_id, instrument_id, symbol, timeframe, pattern_type, name, status, previous_status, end_ts}` bei neuer Erkennung oder Statuswechsel |

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
- **`explanation`**: deterministischer deutscher Erklärtext aus den berechneten Werten (kein KI-Text).

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

`kind` ist relativ zum letzten Schlusskurs: Zone unterhalb = `unterstuetzung`, oberhalb = `widerstand`, Kurs innerhalb = `im_bereich` ("Kurs innerhalb der Zone").

`/patterns/catalog` Eintrag: `{pattern_type, name, direction_if_confirmed, description, criteria: [{key, name, rule, required, weight}], params: [{key, value, unit, description}], algo_version}`.
