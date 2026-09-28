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
