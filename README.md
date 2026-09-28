# Marktmuster-Dashboard

Informations-Tool für Aktien: Nachrichten, Charts, Mustererkennung, Szenarien. **Keine Anlageberatung.** Die Grundregeln stehen in [CLAUDE.md](CLAUDE.md).

Stand: **Phase 1A + 1B (Foundation, Kursdaten-Backend)**. Lauffähig sind Login, Nutzerverwaltung, Datenbank, API, Worker und die Oberfläche mit Hinweis, Dark Mode und deutschen Formaten. Das Backend holt Kursdaten (siehe unten); die Watchlist-/Chart-Oberfläche (1C) folgt in einem eigenen Pull Request.

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
