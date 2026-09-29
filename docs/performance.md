# Messungen Phase 5A

Erzeugt mit `cd backend && python scripts/bench.py` (synthetische Daten in einer temporären SQLite-Datei, nur zur Messung).
Umgebung: Cloud-Container, ein Prozess, 40 Instrumente (35 auf Watchlists von 5 Nutzern), 20.000 Meldungen,
200.000 Einträge in `events`. Die Zahlen sind Größenordnungen, kein Versprechen für andere Rechner.

## Worker-Jobs (laufen alle 5 bis 15 Minuten)

| Job | Lauf mit neuen Daten | Lauf ohne neue Kerzen, vorher | nachher |
|---|---|---|---|
| Mustererkennung | 12,5 s | 12,5 s | 1,8 s |
| Analysen (Ereignisse, Bewegungen) | 18,4 s | 9,1 s | 2,2 s |
| Prognosen | 13,6 s | 1,1 s (hatte schon einen Hash-Vergleich) | 1,1 s |

Der Rest von etwa 2 s je Job ist das Laden der Kerzen (`load_bars`). Ein weiterer Hebel wäre ein billiger
Vorab-Check per SQL; bei dieser Größe lohnt er sich nicht.

## API (Median über 5 Aufrufe, ein Nutzer)

Alle gemessenen Endpunkte antworten unter 100 ms (Kerzen 1m mit 2000 Werten 83 ms, Indikatoren mit fünf
Indikatoren 58 ms, Muster 49 ms, Watchlist mit 15 Instrumenten 14 ms, Nachrichtenliste 9 ms). Die Query-Pläne
der Hauptabfragen (Nachrichtenliste, Zähler, Kerzen, Ereignisse) nutzen vorhandene Indizes, es fehlt kein Index.

## Frontend-Bundle

`npm run build`: 450 kB JavaScript (141 kB gzip), 12,6 kB CSS. Kein Handlungsbedarf.

## Umgesetzt

- Muster- und Analyse-Job überspringen unveränderte Kerzen.
- Kurs- und Intraday-Job pausieren außerhalb der US-Handelszeiten (`app/market_hours.py`).
- `events` wird auf 24 Stunden gekürzt (bei 35 Instrumenten rund 50.000 Zeilen pro Tag).
- Fehlerisolation je Instrument in Kurs-, Intraday- und Tageskerzen-Job.

## Bewusst nicht geändert

- Rate-Limits und Circuit-Breaker je Adapter existierten bereits (`app/adapters/http.py`); die Grenzwerte liegen unter
  den Limits der freien Tarife (Alpaca 150/min, Finnhub 50/min, Yahoo 30/min).
- WebSocket: jede offene Verbindung fragt einmal pro Sekunde `events` per Primärschlüssel ab; für einen Freundeskreis
  reicht das.
