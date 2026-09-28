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

## Phase 2 (News-Backend)

| Regel | Stand | Beleg |
|---|---|---|
| 1 Keine Empfehlungssprache | erfüllt | `test_grundregeln.py` läuft über den neuen Code; erzeugte Begründungen (Lexikon) werden auf verbotene Begriffe geprüft (`test_lexicon_output_has_no_recommendation_language`); Claude-Antworten mit verbotenen Begriffen in Begründung oder Zitat werden verworfen (`test_claude_verify_rejects_invented_quotes_and_forbidden_language`). Zitate aus Originalüberschriften werden unverändert angezeigt |
| 2 Quellentransparenz | erfüllt | `news_items` und `news_instruments` NOT NULL `source_id`/`fetched_at`; jede Meldung liefert Anbieter, Link, Veröffentlichungs- und Abrufzeit (und den ursprünglichen Verlag, falls bekannt); Cluster listen alle Quellen; Stimmung nennt Verfahren und Modell und hat eine eigene Quelle auf der Seite Quellen; `/api/sources` zeigt Beschreibung, Intervall, Verzögerung, Status und Meldungen der letzten 24 h |
| 3 Erklärpflicht | noch nicht anwendbar | keine Muster bis Phase 3 (Stimmung trägt eigene Begründung mit wörtlichen Belegen) |
| 4 Unsicherheit | noch nicht anwendbar | keine Prognosen bis Phase 4 |
| 5 Hinweis auf jeder Seite | unverändert | Frontend-Layout |
| 6 Keine erfundenen Daten | erfüllt | Ohne Schlüssel/Freischaltung: Status `disabled` mit Grund, keine Ersatzmeldungen; Fehler einer Quelle bleiben lokal; Meldungen ohne belegbares Datum oder Link werden verworfen; `empty_reason` nennt Grund und letzten erfolgreichen Abruf |

Offen/ehrlich:
- Alle Adapter wurden nur gegen simulierte Antworten getestet (Mock-Transport); es liegen keine Schlüssel in dieser Umgebung, und die Sandbox erreicht keine Medien-Feeds. Endpunkte und Felder folgen der Anbieterdokumentation aus dem Gedächtnis; ein Lauf mit echten Schlüsseln ist der nächste Prüfschritt.
- RSS-Adressen und Nutzungsbedingungen (tagesschau, CNBC, MarketWatch, Handelsblatt, EQS) sind **nicht verifiziert**. Die Feeds sind deshalb standardmäßig aus und müssen bewusst freigeschaltet werden.
- Das Stimmungs-Lexikon ist eine eigene kleine Wortliste, nicht Loughran-McDonald (Lizenzbedingungen des Originals nicht geprüft). Die Trefferqualität wurde nicht gegen gelabelte Daten gemessen.
- Tageskontingente (Marketaux, Alpha Vantage) werden im Arbeitsspeicher gezählt; ein Neustart des Workers setzt den Zähler zurück.
- Claude-Aufrufe erfolgen einzeln (nicht per Batch-API), Kosten also am oberen Ende der Schätzung im Plan; die Obergrenze gilt trotzdem hart.
