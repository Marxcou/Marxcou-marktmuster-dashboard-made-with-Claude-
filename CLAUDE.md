# Marktmuster-Dashboard (Informations-Tool, KEINE Anlageberatung)

Web-Dashboard: Live-Nachrichten, Live-Charts, regelbasierte Mustererkennung mit vollständiger Erklärung, Prognose-Szenarien mit Unsicherheitsbändern. Oberfläche auf Deutsch (de-DE, Europe/Berlin), Zeitstempel intern in UTC.

## Grundregeln (nicht verhandelbar, für jede Session und jeden Code-Stand)

1. Keine Kauf- oder Verkaufsempfehlungen. Keine Begriffe wie "Kaufen", "Verkaufen", "Strong Buy", "Kursziel" oder Ampelsignale mit Handlungsaufforderung. Nur neutrale, beschreibende Sprache.
2. Vollständige Quellentransparenz: jede Nachricht, jeder Kursdatenpunkt und jede Kennzahl mit Anbietername, Original-Link, Veröffentlichungs- und Abrufzeitpunkt. Eine Seite "Quellen" mit Beschreibung, Intervall, Verzögerung und Status jeder Quelle.
3. Erklärpflicht bei Mustern: Name, Lage im Chart mit Zeitraum, erfüllte Kriterien mit tatsächlichen Werten, Konfidenz-Score mit Berechnungserklärung, mindestens zwei Szenarien mit Bestätigungs- und Ungültigkeitsniveau, historische Trefferquote aus Backtest mit Stichprobengröße.
4. Unsicherheit sichtbar: Prognosen nur als Korridor mit Wahrscheinlichkeitsbereichen, Methode und Backtest-Fehlermaße einsehbar.
5. Auf jeder Seite gut sichtbar: "Dieses Dashboard stellt keine Anlageberatung dar. Alle Analysen sind automatisiert, können fehlerhaft sein und dienen ausschließlich der Information."
6. Keine erfundenen Daten. Fehlende Daten klar anzeigen. Beispieldaten nur im ausdrücklich gekennzeichneten Demo-Modus.

Arbeitsweise: Am Ende jeder Phase selbst prüfen, ob alle Grundregeln eingehalten sind (Ergebnis in `docs/grundregeln-check.md`). API-Schlüssel nur über `.env`, nie im Code und nie in Logs oder gespeicherten Statustexten (siehe unten).

## Wie die Regeln im Code durchgesetzt werden

- Regel 1: `backend/app/grundregeln.py` (Liste verbotener Begriffe) + `backend/tests/test_grundregeln.py` scannt Backend- und Frontend-Quelltexte in CI. Derselbe Filter läuft später zur Laufzeit auf KI-Texten.
- Regel 2: `source_id` und `fetched_at` sind NOT NULL auf jeder Datentabelle; API-Antworten enthalten das `source`-Objekt. Die Quellen-Seite wird aus den Adapter-Metadaten erzeugt (`AdapterMetadata`).
- Regel 3: Eine Erkennung darf nur mit Kriterienliste, Konfidenz-Aufschlüsselung, beiden Szenario-Niveaus und Backtest-Verweis gespeichert werden (Test pro Mustertyp, ab Phase 3).
- Regel 4: Die Prognose-API liefert ausschließlich Quantilbänder (ab Phase 4).
- Regel 5: Der Hinweis ist Teil des App-Layouts (`frontend/src/components/Layout.tsx`), Test prüft jede Route.
- Regel 6: `DEMO_MODE` in `.env`; Demodaten tragen `is_demo=true`, Banner "DEMO-MODUS". Leere Zustände nennen Grund und letzten erfolgreichen Abruf (`empty_reason`).

## Schlüssel in Logs (Regel für jeden neuen Adapter)

- Schlüssel wenn möglich als HTTP-Header senden (z. B. Finnhub `X-Finnhub-Token`), nicht als URL-Parameter.
- `backend/app/log_redaction.py` bereinigt jeden Log-Eintrag (auch Tracebacks) von konfigurierten Geheimwerten und URL-Parametern wie `token`, `apikey`, `api_token`, `key`; httpx/httpcore-Logging steht auf WARNING. Jeder Prozess-Einstieg ruft `install()` auf.
- Statustexte, die in der DB landen oder auf der Quellen-Seite erscheinen, laufen durch `redact()`. Test: `backend/tests/test_log_redaction.py`.

## Struktur

- `backend/` FastAPI (`app/main.py`), Worker (`app/worker.py`), SQLAlchemy 2 + Alembic, Adapter (`app/adapters/`)
- `frontend/` Vite + React + TypeScript + Tailwind
- `docs/api-contract.md` API-Vertrag zwischen Backend und Frontend
- Analysecode ist reines Python (numpy/pandas) ohne I/O, deterministisch, mit versionierten Parametern.

## Befehle

- Alles starten: `docker compose up --build` (nach `cp .env.example .env`)
- Backend: `cd backend && pip install -e ".[dev]" && pytest && ruff check . && mypy app`
- Frontend: `cd frontend && npm ci && npm test && npm run build`
