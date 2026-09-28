# Marktmuster-Dashboard

Informations-Tool für Aktien: Nachrichten, Charts, Mustererkennung, Szenarien. **Keine Anlageberatung.** Die Grundregeln stehen in [CLAUDE.md](CLAUDE.md).

Stand: **Phase 1A (Foundation)**. Lauffähig sind Login, Nutzerverwaltung, Datenbank, API-Gerüst, Worker-Gerüst und die Oberfläche mit Hinweis, Dark Mode und deutschen Formaten. Kursdaten (1B) und Watchlist/Chart-Oberfläche (1C) folgen.

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
