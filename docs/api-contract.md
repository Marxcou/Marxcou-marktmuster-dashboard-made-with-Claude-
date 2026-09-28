# API-Vertrag (Stand Phase 1A)

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
| GET `/instruments/search?q=` | ja | Suche nach Ticker, Name, ISIN in lokal gespeicherten Instrumenten (1B ergänzt Anbieter-Suche/OpenFIGI und speichert Treffer) |
| GET `/instruments/{id}` | ja | Instrument + letzter Kurs (`quote` oder `null`) |
| GET `/instruments/{id}/bars?timeframe=1m\|5m\|1h\|1d&start&end&limit` | ja | `{instrument, timeframe, bars[], empty_reason}` |
| GET `/watchlist` · POST `/watchlist {instrument_id}` · DELETE `/watchlist/{instrument_id}` | ja | Watchlist des Nutzers, Instrumente mit letztem Kurs |
| GET `/sources` | ja | Quellen mit Metadaten und Status (aus Adapter-Metadaten + Health) |
| WS `/ws` | Cookie | Events `{id, type: quote\|news\|detection\|source_status, payload, created_at}` |

## Schnittstellen für die Folge-Workstreams

- **1B (Kursdaten):** implementiert `PriceAdapter` (`backend/app/adapters/base.py`), registriert ihn in `load_builtin_adapters()` (`adapters/registry.py`), hängt Jobs in `JOBS` (`worker.py`) ein, schreibt `Instrument`, `PriceBar`, `Quote` (immer mit `source_id` und `fetched_at`) und ruft `events.publish(db, "quote", {...})` auf. Liefert die Anbieter-Suche über `PriceAdapter.search_instruments` und erweitert `/instruments/search`.
- **1C (Frontend):** ersetzt die Platzhalter in `frontend/src/App.tsx`, nutzt `frontend/src/lib/api.ts` (Typen spiegeln diesen Vertrag) und `lib/format.ts` (de-DE). Layout inkl. Hinweis und Demo-Banner bleibt in `components/Layout.tsx`.
- **Neue Tabellen** kommen je Workstream per eigener Alembic-Migration (`cd backend && alembic revision --autogenerate`).
