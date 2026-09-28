# Grundregel-Check

## Phase 1A (Foundation)

| Regel | Stand | Beleg |
|---|---|---|
| 1 Keine Empfehlungssprache | erfüllt | `backend/tests/test_grundregeln.py` scannt Backend und Frontend |
| 2 Quellentransparenz | Gerüst erfüllt | NOT NULL `source_id`/`fetched_at`, `source` in API-Antworten; Quellen-Seite folgt in 2D, `/api/sources` existiert |
| 3 Erklärpflicht | noch nicht anwendbar | keine Muster bis Phase 3 |
| 4 Unsicherheit | noch nicht anwendbar | keine Prognosen bis Phase 4 |
| 5 Hinweis auf jeder Seite | erfüllt | `Layout.tsx`, Test pro Route in `frontend/src/app.test.tsx` |
| 6 Keine erfundenen Daten | erfüllt | keine Beispieldaten im Code; `empty_reason` statt Platzhaltern; `DEMO_MODE`-Banner |

## Phase 1C (Frontend: Login, Watchlist, Suche, Chart)

| Regel | Stand | Beleg |
|---|---|---|
| 1 Keine Empfehlungssprache | erfüllt | Texte neutral, Farben nur Auf/Ab; CI-Scan grün |
| 2 Quellentransparenz | erfüllt | `SourceTip` an Kurs und Chart (Anbieter, Link, Wert- und Abrufzeit, Verzögerung, Bedingungen) |
| 5 Hinweis auf jeder Seite | erfüllt | Test für `/`, `/login`, `/quellen`, `/instrument/1`, 404 |
| 6 Keine erfundenen Daten | erfüllt | Leerzustände mit `empty_reason` (Chart), "Kein Kurs verfügbar" (Karte), Demo-Kennzeichnung an Kurs/Chart; News- und Muster-Zähler als "noch nicht angebunden" ausgewiesen |

## Phase 1B (Kursdaten-Backend)

| Regel | Stand | Beleg |
|---|---|---|
| 1 Keine Empfehlungssprache | erfüllt | `test_grundregeln.py` läuft über den neuen Code |
| 2 Quellentransparenz | erfüllt | Jede Kerze/Quote wird nur mit `source_id` und `fetched_at` gespeichert (`price_service.py`); `/bars` und Quotes tragen `source`; Adapter-Metadaten (Intervall, Verzögerung, Schlüsselpflicht) speisen `/sources`; Health wird aktiv geprüft |
| 3 Erklärpflicht | noch nicht anwendbar | keine Muster bis Phase 3 |
| 4 Unsicherheit | noch nicht anwendbar | keine Prognosen bis Phase 4 |
| 5 Hinweis auf jeder Seite | unverändert (1A) | Frontend-Layout |
| 6 Keine erfundenen Daten | erfüllt | Ausfall/fehlender Schlüssel führt zu Status und leerem Ergebnis, nie zu Ersatzwerten (`test_failing_adapter_falls_through_without_invented_data`); Stooq-Hinweistexte werden nicht als CSV gelesen; XETRA-Intraday zeigt `empty_reason`; IEX-Abweichung und "Handelsende" stehen in den Quellen-Metadaten |

Offen/ehrlich: Die Adapter wurden gegen simulierte Antworten (Mock-Transport) getestet, nicht gegen die echten Dienste, da keine Schlüssel in dieser Umgebung liegen. Endpunkte und Felder folgen der Anbieterdokumentation; ein Lauf mit echten Schlüsseln ist der nächste Prüfschritt.
