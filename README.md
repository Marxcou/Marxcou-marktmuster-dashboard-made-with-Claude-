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
| Investor-Relations-Feeds | `IR_FEEDS` | **standardmäßig aus**: Adresse und Nutzungsbedingungen je IR-Seite zuerst prüfen |
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
- **Historische Trefferquote:** kommt aus dem Muster-Backtest (siehe unten, Tabelle `backtest_runs`). Solange er nicht gelaufen ist, zeigt die API `"status": "nicht_berechnet"` ohne Zahlen.

Alle Parameter mit Beschreibung stehen in `backend/app/analysis/params.py` und unter `GET /api/patterns/catalog`; jede Erkennung speichert die verwendeten Werte, `params_hash` und `algo_version`. Endpunkte: `GET /api/instruments/{id}/patterns`, `/api/patterns/{id}`, `/api/patterns/counts`. Tests mit synthetischen Kursreihen bekannten Ergebnisses: `backend/tests/test_patterns.py`, `test_pattern_api.py`.

## Muster-Backtest (Phase 3C)

Die historische Trefferquote je Mustertyp wird mit echten Tagesdaten berechnet. Der Backtest ist ein einmaliger Job (nicht im Worker-Zeitplan) und nimmt die erste eingerichtete Tagesdatenquelle: **Stooq**, wenn `STOOQ_API_KEY` gesetzt ist, sonst **Yahoo Finance (inoffiziell)**, wenn `YAHOO_ENABLED=true` gesetzt ist. Mit `--source stooq` oder `--source yahoo` lässt sich die Quelle erzwingen. Ein Lauf nutzt genau eine Quelle; sie steht im Ergebnis (`metrics.source`, Text "Tagesdaten von …") und in der Musteransicht neben der Trefferquote. Ist keine Quelle eingerichtet oder liefert sie nichts, rechnet und speichert der Job nichts; bis zum ersten Lauf zeigt das Dashboard "nicht berechnet".

Yahoo ist inoffiziell: Es gibt keine dokumentierte API, der Abruf kann ohne Ankündigung ausfallen, und die Nutzungsbedingungen erlauben diese Nutzung nicht ausdrücklich. Die Kurse sind splitbereinigt, nicht dividendenbereinigt.

```bash
# erst mit zwei Werten ausprobieren, ohne etwas zu speichern
docker compose run --rm worker python -m app.backtest_job --symbols SAP.XETR,AAPL.XNAS --dry-run
# vollständiger Lauf (DAX-Auswahl und 100 US-Werte ab 2010), Ergebnis landet in der Datenbank
docker compose run --rm worker python -m app.backtest_job
```

Ohne Docker: `cd backend && python -m app.backtest_job` (gleiche Optionen). Der vollständige Lauf lädt ca. 140 Tagesreihen (Stooq: 20 Abrufe je Minute, also ca. 7 Minuten; Yahoo: höchstens 30 je Minute) und rechnet ca. 1 CPU-Minute je Aktie, verteilt auf alle Kerne bis auf einen (`--workers`). Die geladenen Daten liegen 7 Tage im Zwischenspeicher `BACKTEST_CACHE_DIR`, ein zweiter Lauf fragt die Quelle also nicht erneut (getrennt je Quelle). Weitere Optionen: `--source`, `--start`, `--horizon` (Kerzen, Standard 20), `--min-move` (%, Standard 5), `--step`, `--window`, `--universe-file` (eigene Liste, je Zeile `SYMBOL,BÖRSE`), `python -m app.backtest_job --help`.

So wird gerechnet (`backend/app/analysis/backtest.py`):

- **Ohne Blick in die Zukunft:** Die Mustererkennung läuft schrittweise (alle 5 Kerzen) nur auf den Kerzen bis zum jeweiligen Tag (höchstens 500). Ein Fall ist ein bestätigtes Muster. Ausgangspunkt ist der Schlusskurs am Tag der Bestätigung oder, falls das Muster erst später sichtbar war, an diesem späteren Tag.
- **Treffer:** Ein Schlusskurs innerhalb von 20 Kerzen liegt mindestens 5 % in Richtung des Musters (beim symmetrischen Dreieck in Richtung des Ausbruchs).
- **Basisrate:** derselbe Test für jeden Handelstag derselben Aktien im selben Zeitraum, gewichtet wie die Fälle. Das 95-%-Intervall der Trefferquote kommt aus der Wilson-Formel. Liegt seine untere Grenze nicht über der Basisrate, zeigt das Dashboard "Historisch nicht besser als Zufall".
- **Szenarien:** Für "Bestätigung"/"Scheitern" (bzw. "Ausbruch nach oben/unten") zählt, wie oft Muster, die in Bildung erkannt wurden, später bestätigt oder ungültig wurden.
- **Ausgeschlossen:** Zeiträume mit einem Tagessprung über 40 % (z. B. nicht bereinigte Aktiensplits) und Fälle, nach denen noch keine 20 Kerzen vorliegen. Beides wird gezählt und gespeichert.
- **Offen gesagt:** Die Aktienauswahl sind heutige Indexmitglieder (Survivorship Bias). Fälle derselben Aktie überschneiden sich zeitlich, das Intervall ist daher eher zu schmal. Die DAX-Liste in `backend/app/backtest_universe.py` ist nach bestem Wissen (Stand 2025) und sollte vor dem Lauf geprüft werden.

Jeder Lauf speichert je Mustertyp eine Zeile in `backtest_runs` mit Parametern, Zeitraum, Quelle, Abrufzeit, verwendeten und fehlenden Werten. Das Dashboard zeigt immer den neuesten Lauf. Tests mit synthetischen Kursreihen bekannten Ergebnisses: `backend/tests/test_backtest.py`.
## Prognosen und Prognosegüte (Phase 4A, Backend)

Der Worker rechnet alle 15 Minuten für alle Watchlist-Instrumente (nur abgeschlossene Tageskerzen, ab 250 Kerzen) einen Prognose-Korridor über 20 Handelstage, aber nur neu, wenn sich Kerzen, Muster oder Backtest geändert haben:

- **Hauptmethode:** Monte-Carlo-Simulation per Block-Bootstrap (4.000 Pfade aus Blöcken von 10 historischen Tagesrenditen der letzten 750 Tage, Trend entfernt). Ergebnis sind nur Quantile (2,5/10/25/50/75/90/97,5 %) je Tag, also die Bänder 50/80/95 %; es gibt keine einzelne Prognoselinie.
- **Vergleich:** ARIMA(1,1,0) auf Log-Kursen (eigene numpy-Umsetzung, Kleinste-Quadrate, normalverteilte Fehler).
- **Prognose-Backtest:** rollierender Ursprung auf der eigenen Historie (alle 5 Tage ein Prüfzeitpunkt, bis 300), ohne Vorgriff. Gemessen werden Abdeckung der Bänder, mittlerer absoluter Fehler des Medians und Pinball-Verlust, jeweils gegen die naive Referenz "Kurs bleibt gleich", für 5, 10 und 20 Tage. "Besser als naiv" gilt nur bei kleinerem Fehler und Diebold-Mariano-Test p < 0,05; sonst steht offen "nicht nachweisbar genauer". Ergebnisse liegen in `backtest_runs` (`kind = "forecast"`).
- **Muster-Szenarien:** für Muster "in Bildung" der Anteil simulierter Pfade, die das Bestätigungs- bzw. Ungültigkeitsniveau zuerst erreichen, neben der historischen Quote aus dem Muster-Backtest. Die Simulation kennt das Muster nicht; das steht in der Antwort.

Code: `backend/app/analysis/forecast.py` (reines numpy, deterministischer Seed je Datenstand), `backend/app/forecast_service.py`, `backend/app/api/forecasts.py`. Endpunkte: `GET /api/instruments/{id}/forecast`, `GET /api/forecasts/methods`. Tests: `backend/tests/test_forecast.py`, `test_forecast_api.py`.

## Prognosekorridor im Frontend (Phase 4B)

Auf der Chart-Seite (Tageskerzen) lässt sich der **Prognosekorridor** zuschalten: drei verschachtelte Wahrscheinlichkeitsbereiche (50, 80 und 95 %) hinter der letzten Kerze, nie eine Einzellinie. Darunter das Panel mit den Werten am Ende des Horizonts (5, 10 oder 20 Kerzen), "Wie wird das berechnet?" (Methode, Annahmen, Grenzen, Parameter), der **Prognosegüte** aus dem Backtest (Abdeckung der Bänder, Fehlermaße gegen die naive Referenz "Kurs bleibt gleich", Stichprobe, Signifikanztest) und dem Vergleichsverfahren ARIMA. Wird ein Muster gewählt, erscheinen seine Bestätigungs- und Ungültigkeitsniveaus als Linien bis zum Ende des Korridors, dazu Lage im Korridor, simulierte Pfadanteile und die historische Quote aus dem Muster-Backtest nebeneinander. Fehlt die Prognose oder der Backtest, steht das mit Grund da; ist die Methode nicht nachweisbar besser als die Referenz, steht auch das. Code: `frontend/src/components/ForecastPanel.tsx`, `frontend/src/lib/forecast.ts`, Tests `frontend/src/forecast.test.tsx`; Vertrag: `docs/api-contract.md`, Abschnitt "Phase 4A".

## Kursdaten (Phase 1B)

| Quelle | Umfang | Schlüssel in `.env` |
|---|---|---|
| Alpaca (IEX) | US: Live-Kurse per WebSocket, Kerzen 1m/5m/1h/1d | `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY` |
| Finnhub | US: Kurs als Ausweichquelle | `FINNHUB_API_KEY` |
| Stooq | Tagesdaten US und XETRA | `STOOQ_API_KEY` |
| Yahoo Finance (inoffiziell) | Tagesdaten US und XETRA, wenn Stooq fehlt | `YAHOO_ENABLED=true` (kein Schlüssel) |
| OpenFIGI | Suche nach Ticker, Name, ISIN | optional `OPENFIGI_API_KEY` |

Der Worker holt Daten nur für Aktien, die auf mindestens einer Watchlist stehen. Fehlt ein Schlüssel, zeigt `/api/sources` den Status `disabled`; es werden keine Ersatzdaten erzeugt. XETRA hat im kostenlosen Tarif nur Tagesdaten: 1T/1W zeigen dafür einen ausdrücklichen Hinweis. Kurse aus dem Alpaca-Live-Feed stammen von der IEX-Börse und können vom konsolidierten Kurs abweichen. Ein Ausfall einer Quelle bleibt lokal (Rate-Limit, Retry, Circuit-Breaker je Adapter).

## Starten (Docker Compose)

Voraussetzung: Docker mit Compose.

```bash
cp .env.example .env        # .env liegt im Projektwurzelverzeichnis, neben docker-compose.yml
# In .env mindestens SESSION_SECRET, ADMIN_EMAIL und ADMIN_PASSWORD setzen, dann API-Schlüssel eintragen
docker compose up --build
```

**Hinweis zu `.env`:** Schreibe keine Kommentare hinter einen Wert (`KEY=   # Text`). Docker Compose übernimmt den Kommentar sonst als Wert. Kommentare gehören in eine eigene Zeile darüber. Wenn du deine `.env` aus einer älteren `.env.example` kopiert hast, entferne solche Kommentare oder kopiere die Vorlage neu. Das Backend behandelt Werte, die mit `#` beginnen, als nicht gesetzt (Warnung im Log), und ungültige `IR_FEEDS`/`EQS_RSS_URL` erscheinen auf der Seite Quellen als "ungültig, deaktiviert".

Dann im Browser `http://localhost:8080` öffnen (Port über `WEB_PORT`). Der erste Admin wird beim Start aus `ADMIN_EMAIL`/`ADMIN_PASSWORD` angelegt. Das geschieht nur beim allerersten Start, solange noch kein Admin existiert; die Platzhalter aus `.env.example` (`admin@example.com`, `change-me-now`) werden abgelehnt (Hinweis im Log des `api`-Containers). Ein vorhandener Admin wird nie automatisch überschrieben, auch nicht, wenn du das Passwort in der App geändert hast. Weicht `ADMIN_EMAIL` vom vorhandenen Admin ab, steht eine Warnung im Log.

Hast du `.env` erst nach dem ersten Start angepasst und kommst nicht hinein, übernimmt dieser Befehl die Werte aus `.env` in die bestehende Datenbank (ohne sie zu löschen):

```bash
docker compose run --rm api python -m app.admin_cli
``` Weitere Nutzer legt ein Admin an (`POST /api/users`); es gibt keine offene Registrierung.

### Benutzerverwaltung (Admin)

Als Administrator erscheint im Menü **Benutzer**. Dort kannst du Konten anlegen (E-Mail, Anzeigename, Rolle), sperren und wieder entsperren und Passwörter zurücksetzen. Ablauf für einen Freund:

1. **Konto anlegen**: das Dashboard zeigt ein Einmalpasswort genau einmal an. Es wird nicht gespeichert und nicht per E-Mail verschickt (es gibt keinen Mailversand), gib es selbst weiter.
2. Beim ersten Login muss der Freund ein eigenes Passwort festlegen (mindestens 10 Zeichen); bis dahin ist nur diese Seite erreichbar. Jeder Nutzer kann sein Passwort später unter seinem Namen oben rechts ändern; dabei werden seine anderen Sitzungen beendet.
3. **Sperren** beendet sofort alle Sitzungen des Kontos, Anmeldung und Live-Verbindung sind danach nicht mehr möglich. **Passwort zurücksetzen** erzeugt ein neues Einmalpasswort und beendet ebenfalls alle Sitzungen.
4. Der letzte aktive Admin und das eigene Konto lassen sich nicht sperren oder herabstufen.

API-Schlüssel stehen nur in der `.env` des Servers. Kein Endpunkt und keine Seite liefert sie an einen Browser (auch nicht an Admins); ein Test prüft das für alle GET-Routen. Manche kostenlose Datentarife erlauben nur private Nutzung, bitte vor dem Teilen die Nutzungsbedingungen prüfen (Seite "Quellen"). Das Claude-Budget gilt für alle Nutzer zusammen. Aktualisieren: `docker compose up --build` (die Migration `0007` läuft beim Start).

### Windows: Zeilenenden

Die Datei `.gitattributes` erzwingt LF für Skripte und Konfigurationsdateien, die in den Linux-Containern laufen. Zusätzlich entfernt `backend/Dockerfile` beim Bauen eventuelle CRLF aus `entrypoint.sh`. Trat vorher `exec ./entrypoint.sh: no such file or directory` auf, in einem bestehenden Klon nach dem Pull einmal ausführen:

```bash
git pull
git add --renormalize .
git status                  # sollte nichts Relevantes zeigen
docker compose up --build -d
```

Falls Dateien im Arbeitsverzeichnis weiterhin CRLF haben: `git rm --cached -r . && git reset --hard` (verwirft lokale, nicht committete Änderungen).

`.env` wird nie committet. Schlüssel gehören ausschließlich dorthin. Schlüssel erscheinen weder in Logs noch in Statustexten der Quellen-Seite: Logeinträge werden zentral bereinigt (`backend/app/log_redaction.py`), das HTTP-Client-Logging von httpx steht auf WARNING, und wo der Anbieter es unterstützt, geht der Schlüssel im Header statt in der URL. Wer die Logs vor der Umstellung geteilt hat oder Logs aus einer älteren Version aufbewahrt, sollte die betroffenen Schlüssel beim Anbieter erneuern.

## Entwicklung ohne Docker

```bash
cd backend && pip install -e ".[dev]" && pytest && ruff check . && mypy app
cd frontend && npm ci && npm test && npm run build
```

## Aufbau

`backend/` (FastAPI, Worker, Alembic, Adapter), `frontend/` (Vite, React, TypeScript, Tailwind), `docs/api-contract.md` (API-Vertrag), `docs/grundregeln-check.md` (Selbstprüfung je Phase).
