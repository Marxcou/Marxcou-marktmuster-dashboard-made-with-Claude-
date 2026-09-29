# Marktmuster-Dashboard

Informations-Tool für Aktien: Nachrichten, Charts, Mustererkennung, Szenarien. **Keine Anlageberatung.** Die Grundregeln stehen in [CLAUDE.md](CLAUDE.md).

Stand: **Phase 1A + 1B (Foundation, Kursdaten-Backend) und Phase 2 Backend (News-Aggregator)**. Lauffähig sind Login, Nutzerverwaltung, Datenbank, API, Worker und die Oberfläche mit Hinweis, Dark Mode und deutschen Formaten. Das Backend holt Kursdaten (siehe unten); die Watchlist-/Chart-Oberfläche (1C) folgt in einem eigenen Pull Request.

## Nachrichten (Phase 2, Backend)

Der Worker ruft je Quelle in eigenem Intervall Meldungen zu den Aktien aller Watchlists ab, ordnet sie Instrumenten zu (Anbieter-Symbol, ISIN, Ticker, Firmenname; der Grund steht je Zuordnung dabei), führt Duplikate zu Clustern zusammen (normalisierte URL, Titelähnlichkeit innerhalb von 48 Stunden, **alle** Quellen eines Clusters bleiben sichtbar) und bewertet die Stimmung mit Begründung und Modellangabe. Gespeichert werden nur Überschrift, ein Auszug von höchstens 300 Zeichen und der Link. Endpunkte: `/api/news`, `/api/instruments/{id}/news`, `/api/news/counts`, `/api/news/sentiment-status`, `/api/sources` (siehe `docs/api-contract.md`).

| Quelle | Schlüssel in `.env` | Hinweis |
|---|---|---|
| Finnhub Unternehmensnachrichten | `FINNHUB_API_KEY` (derselbe wie für Kurse) | nur US, alle 5 Min. |
| SEC EDGAR | `SEC_EDGAR_CONTACT_EMAIL` | Pflichtmeldungen (8-K, 10-Q, 10-K, Form 4), Kontaktadresse ist Pflicht im User-Agent |
| Marketaux | `MARKETAUX_API_KEY` | 100 Anfragen/Tag: Aktien werden reihum abgefragt, höchstens 90 Anfragen/Tag |
| Alpha Vantage News (optional) | `ALPHAVANTAGE_API_KEY` | 25 Anfragen/Tag, höchstens 20 genutzt |
| GDELT | keiner | verrauscht: Meldungen ohne Firmenname oder Ticker im Titel werden verworfen |
| RSS-Feeds, EQS | `RSS_ENABLED_FEEDS`, `EQS_RSS_URL` | **standardmäßig aus**: Adresse und Nutzungsbedingungen zuerst prüfen |

Quellen ohne Schlüssel bzw. ohne Freischaltung erscheinen auf der Seite Quellen als "deaktiviert" mit Grund; ein Ausfall einer Quelle beeinträchtigt die anderen nicht.

**Stimmung:** Immer verfügbar ist ein regelbasiertes Wortlisten-Verfahren (Deutsch/Englisch, ohne Kosten). Mit `ANTHROPIC_API_KEY` bewertet Claude Haiku 4.5 die Meldungen und muss die auslösenden Formulierungen wörtlich zitieren; das Backend prüft jedes Zitat gegen den Text und fällt bei Abweichung auf das Lexikon zurück. `CLAUDE_MONTHLY_BUDGET_USD` (Standard 10) ist eine harte Obergrenze: vor jedem Aufruf wird der Verbrauch des Monats plus der Höchstwert des Aufrufs geprüft. Danach gilt das Lexikon, sichtbar in `/api/news/sentiment-status` und auf der Seite Quellen. Bitte zusätzlich ein Ausgabenlimit in der Anthropic-Konsole setzen.

**Claude per Batch-API (Standard, `CLAUDE_USE_BATCH=true`):** Neue Meldungen erscheinen sofort mit der Lexikon-Stimmung; Claude wird parallel per Batch-API (halber Preis) angefragt und ersetzt sie, sobald das Ergebnis da ist (meist Minuten, spätestens nach 24 Stunden). Die Prüfung der Zitate ist dieselbe wie bei Einzelaufrufen. Für offene Batches wird der Höchstbetrag gegen das Monatslimit vorgemerkt. Nicht belegbare Antworten bleiben beim Lexikon und werden nicht erneut angefragt; abgelaufene Anfragen werden erneut eingereicht. Mit `CLAUDE_USE_BATCH=false` gilt der frühere Einzelaufruf.

**Tageskontingente:** Der Zähler für Marketaux und Alpha Vantage liegt in der Tabelle `api_usage` und übersteht Neustarts (Tageswechsel 00:00 UTC).

**Aufbewahrung:** Ein täglicher Job löscht Cluster, deren letzte Meldung älter als `NEWS_RETENTION_DAYS` (Standard 90, Minimum 14, 0 = aus) ist, samt Meldungen, Zuordnung und Stimmung.

## Indikatoren und Ereignisse (Phase 3A, Backend)

Der Worker wertet für alle Watchlist-Instrumente (Zeitrahmen 1d und 1h, nur abgeschlossene Kerzen) alle 5 Minuten aus:

- **Indikatoren für den Chart** (`GET /api/instruments/{id}/indicators`): SMA, EMA, RSI (Wilder), MACD, Bollinger-Bänder, on the fly aus den gespeicherten Kerzen berechnet. Formeln stehen in der Antwort und in `backend/app/analysis/indicators.py`.
- **Indikator-Ereignisse** (`/indicator-events`): Golden/Death Cross (SMA 50/200), RSI-Divergenz, Bollinger-Ausbruch, Volumenspitze. Jedes Ereignis nennt Kriterien mit tatsächlichen Werten, Parameter, Algorithmus-Version und die Kursquellen. Eine historische Trefferquote gibt es dafür noch nicht (kommt mit dem Backtest); die Antwort sagt das ausdrücklich.
- **Auffällige Kursbewegungen und Meldungen** (`/move-links`): Rendite- oder Volumen-Ausreißer (z-Wert ≥ 3 gegenüber den 60 Vorkerzen), zeitlich zugeordnet zu Meldungen desselben Instruments. Rein zeitlich, ohne Aussage über Ursache.

Parameter stehen in `backend/app/analysis/events.py` (`PARAMS`) und `moves.py`; Tests mit synthetischen Reihen in `backend/tests/test_indicator_events.py`. Vertrag: `docs/api-contract.md`.

## Mustererkennung (Phase 3B, Backend)

Der Worker sucht alle 5 Minuten für alle Watchlist-Instrumente (1d und 1h, nur abgeschlossene Kerzen, bis 1.500 Kerzen) regelbasiert und deterministisch nach Chartmustern:

- **Muster:** Kopf-Schulter (auch invers), Doppelhoch/Doppelboden, Dreiecke (aufsteigend, absteigend, symmetrisch), Keile (steigend, fallend), Flaggen und Wimpel (nach Anstieg/Rückgang). Grundlage sind Wendepunkte per ZigZag mit ATR-Schwelle (`backend/app/analysis/pivots.py`).
- **Unterstützungs- und Widerstandszonen** aus Häufungen von Wendepunkten (`backend/app/analysis/zones.py`).
- **Erklärung je Erkennung:** Lage (Schlüsselpunkte, Linien, Zeitraum), jedes Kriterium mit Regel und tatsächlichem Wert, Konfidenz als gewichteter Mittelwert der Teilwerte mit Aufschlüsselung, Szenarien "Bestätigung"/"Scheitern" mit Kursniveau (keine Kursziele), Status (in Bildung, bestätigt, ungültig) mit Begründung.
- **Historische Trefferquote:** kommt aus dem Muster-Backtest (3C, Tabelle `backtest_runs`). Bis dahin zeigt die API `"status": "nicht_berechnet"` ohne Zahlen.

Alle Parameter mit Beschreibung stehen in `backend/app/analysis/params.py` und unter `GET /api/patterns/catalog`; jede Erkennung speichert die verwendeten Werte, `params_hash` und `algo_version`. Endpunkte: `GET /api/instruments/{id}/patterns`, `/api/patterns/{id}`, `/api/patterns/counts`. Tests mit synthetischen Kursreihen bekannten Ergebnisses: `backend/tests/test_patterns.py`, `test_pattern_api.py`.

## Kursdaten (Phase 1B)

| Quelle | Umfang | Schlüssel in `.env` |
|---|---|---|
| Alpaca (IEX) | US: Live-Kurse per WebSocket, Kerzen 1m/5m/1h/1d | `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY` |
| Finnhub | US: Kurs als Ausweichquelle | `FINNHUB_API_KEY` |
| Stooq | Tagesdaten US und XETRA | `STOOQ_API_KEY` |
| OpenFIGI | Suche nach Ticker, Name, ISIN | optional `OPENFIGI_API_KEY` |

Der Worker holt Daten nur für Aktien, die auf mindestens einer Watchlist stehen. Fehlt ein Schlüssel, zeigt `/api/sources` den Status `disabled`; es werden keine Ersatzdaten erzeugt. XETRA hat im kostenlosen Tarif nur Tagesdaten: 1T/1W zeigen dafür einen ausdrücklichen Hinweis. Kurse aus dem Alpaca-Live-Feed stammen von der IEX-Börse und können vom konsolidierten Kurs abweichen. Ein Ausfall einer Quelle bleibt lokal (Rate-Limit, Retry, Circuit-Breaker je Adapter).

## Starten (Docker Compose)

Voraussetzung: Docker mit Compose.

```bash
cp .env.example .env        # .env liegt im Projektwurzelverzeichnis, neben docker-compose.yml
# In .env mindestens SESSION_SECRET, ADMIN_EMAIL und ADMIN_PASSWORD setzen, dann API-Schlüssel eintragen
docker compose up --build
```

Dann im Browser `http://localhost:8080` öffnen (Port über `WEB_PORT`). Der erste Admin wird beim Start aus `ADMIN_EMAIL`/`ADMIN_PASSWORD` angelegt. Weitere Nutzer legt ein Admin an (`POST /api/users`); es gibt keine offene Registrierung.

`.env` wird nie committet. Schlüssel gehören ausschließlich dorthin.

## Entwicklung ohne Docker

```bash
cd backend && pip install -e ".[dev]" && pytest && ruff check . && mypy app
cd frontend && npm ci && npm test && npm run build
```

## Aufbau

`backend/` (FastAPI, Worker, Alembic, Adapter), `frontend/` (Vite, React, TypeScript, Tailwind), `docs/api-contract.md` (API-Vertrag), `docs/grundregeln-check.md` (Selbstprüfung je Phase).
