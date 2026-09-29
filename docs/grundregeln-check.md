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
- Investor-Relations-Feeds (`IR_FEEDS`): keine Adresse ist voreingestellt, Feeds sind aus, bis Luca Adresse und Nutzungsbedingungen je IR-Seite geprüft und eingetragen hat.
- RSS-Adressen und Nutzungsbedingungen (tagesschau, CNBC, MarketWatch, Handelsblatt, EQS) sind **nicht verifiziert**. Die Feeds sind deshalb standardmäßig aus und müssen bewusst freigeschaltet werden.
- Das Stimmungs-Lexikon ist eine eigene kleine Wortliste, nicht Loughran-McDonald (Lizenzbedingungen des Originals nicht geprüft). Die Trefferqualität wurde nicht gegen gelabelte Daten gemessen.
- Tageskontingente (Marketaux, Alpha Vantage) werden im Arbeitsspeicher gezählt; ein Neustart des Workers setzt den Zähler zurück.
- Claude-Aufrufe erfolgen einzeln (nicht per Batch-API), Kosten also am oberen Ende der Schätzung im Plan; die Obergrenze gilt trotzdem hart.

## Phase 3A (Indikatoren, Indikator-Ereignisse, News↔Kurs, Backend)

| Regel | Stand | Beleg |
|---|---|---|
| 1 Keine Empfehlungssprache | erfüllt | `test_grundregeln.py` scannt den neuen Code; alle erzeugten Titel, Zusammenfassungen und Kriterien werden im Test `test_every_event_carries_explanation_and_neutral_language` auf verbotene Begriffe geprüft; Richtungen heißen `up`/`down` und beschreiben nur die Lage der Werte |
| 2 Quellentransparenz | erfüllt | Indikator-Antworten, Ereignisse und Bewegungen nennen `sources` (Anbieter, Link, Bedingungen, Verzögerung) und `bars_fetched_at`; Tabellen haben NOT NULL `source_id`/`fetched_at`; verknüpfte Meldungen tragen alle Quellen ihres Clusters |
| 3 Erklärpflicht | für Indikator-Ereignisse erfüllt, soweit anwendbar | Jedes Ereignis speichert Kriterien mit Regel, Sollwert und tatsächlichem Wert sowie Parameter und Version (Test pro Ereignistyp). Szenarien, Konfidenz-Score und Backtest-Trefferquote gehören zu Chartmustern (3B/3C) und sind für Indikator-Ereignisse nicht vorgesehen; `historical_stats` ist `null` mit ausdrücklicher Begründung statt erfundener Zahlen |
| 4 Unsicherheit | noch nicht anwendbar | keine Prognosen bis Phase 4 |
| 5 Hinweis auf jeder Seite | unverändert | Frontend-Layout |
| 6 Keine erfundenen Daten | erfüllt | Ohne Volumen der Quelle entstehen keine Volumen-Ereignisse; die laufende Kerze wird nie ausgewertet; leere Antworten tragen `empty_reason`; zu kurze Reihen liefern `null`-Werte statt Schätzungen; keine Beispieldaten |

Offen/ehrlich:
- Die Parameter (SMA 50/200, RSI 14, Pivot-Fenster 5, z-Schwelle 3, Zeitfenster für Meldungen) sind übliche Voreinstellungen, nicht an Daten optimiert. Die Zeitfenster der Meldungs-Zuordnung sind eine Festlegung ohne empirische Prüfung.
- Die Indikatoren wurden gegen bekannte Referenzwerte (RSI-Beispiel von StockCharts) und analytische Fälle getestet, nicht gegen eine andere Bibliothek auf Echtdaten. Ein Lauf mit echten Kursdaten steht noch aus.
- Bollinger-Bänder nutzen die Standardabweichung der Grundgesamtheit (ddof=0), wie in der Literatur üblich; andere Charting-Tools weichen ggf. leicht ab.
- Unterstützungs-/Widerstandszonen aus dem Plan (3A) gehören zur Muster-Engine (3B) und sind hier nicht enthalten.
## Phase 3D (Frontend: Indikatoren, Muster, Erklärpanel)

| Regel | Stand | Beleg |
|---|---|---|
| 1 Keine Empfehlungssprache | erfüllt | `test_grundregeln.py` läuft über den neuen Code. Farben sind rein beschreibend (Muster violett, Ereignisse cyan), keine Ampeln. Bestätigungs- und Ungültigkeitsniveau sind ausdrücklich als "keine Kursziele" beschriftet |
| 2 Quellentransparenz | erfüllt | Unter dem Chart stehen Kursquellen, Abrufzeit, Verfahrensversion und Formel der eingeblendeten Indikatoren; Muster, Ereignisse und Bewegungen haben je ein aufklappbares Quellenfeld mit `SourceTip` |
| 3 Erklärpflicht | erfüllt (Anzeige) | `PatternPanel` zeigt Name, Zeitraum, Schlüsselpunkte, Kriterien mit tatsächlichen Werten, Konfidenz mit Berechnung und Aufschlüsselung, mindestens zwei Szenarien mit Niveaus und den Backtest. Fehlt einer dieser Teile, erscheint eine rote Warnung "unvollständig erklärt" (`patterns.test.tsx`) |
| 4 Unsicherheit | noch nicht anwendbar | Prognosen folgen in Phase 4 |
| 5 Hinweis auf jeder Seite | unverändert | Layout, Test über alle Routen |
| 6 Keine erfundenen Daten | erfüllt | Fehlende Endpunkte (404), fehlender Backtest, fehlende Indikatorwerte (Einschwingphase bleibt leer) und nicht unterstützte Zeitraster (Muster nur 1d/1h) werden mit Grund angezeigt; nie Platzhalterwerte |

Offen/ehrlich:
- Die Oberfläche wurde gegen den Vertrag aus den Branches `phase-3a-indicators` und `phase-3-pattern-engine` gebaut und mit simulierten Antworten geprüft (Vitest und eine Sichtprüfung mit Mock-Daten im Browser), nicht gegen das laufende Backend.
- Die Warnschwelle "kleine Stichprobe" (weniger als 30 Fälle) ist eine Annahme der Oberfläche, kein Wert aus dem Backtest.
- Der Vertrag für den Muster-Backtest (3C) steht noch aus; das Frontend liest die Felder aus 3B (`backtest`).
- Claude-Stimmung läuft standardmäßig per Batch-API (halber Preis, verzögerte Ergebnisse, bis dahin Lexikon-Stimmung mit sichtbarem Verfahren). Wie in Phase 2 nur gegen simulierte Antworten getestet; das Batch-Antwortformat folgt der Anbieterdokumentation und ist mit echtem Schlüssel noch zu prüfen.

## Phase 3B (Muster-Engine, Backend)

| Regel | Stand | Beleg |
|---|---|---|
| 1 Keine Empfehlungssprache | erfüllt | `test_grundregeln.py` läuft über den neuen Code; alle erzeugten Texte (Kriterien, Szenarien, Status, Erklärung) werden je Mustertyp auf verbotene Begriffe geprüft (`test_explanation_duty_for_every_pattern_type`). Richtungen heißen `aufwärts`/`abwärts`/`offen`. Es gibt keine Kursziele und keine Measured-Move-Projektion; Szenarien nennen nur das Bestätigungs- bzw. Ungültigkeitsniveau |
| 2 Quellentransparenz | erfüllt | `pattern_detections` und `sr_zones` haben NOT NULL `source_id`/`fetched_at` plus `source_ids`; die API liefert `data_basis` (Zeitraum, Kerzenanzahl, letzter Abruf, Quellen) je Antwort und je Erkennung |
| 3 Erklärpflicht | erfüllt (Backend), Trefferquote folgt mit 3C | Jede Erkennung hat Name, Zeitraum, Schlüsselpunkte, Linien, alle Kriterien mit Regel und tatsächlichem Wert, Konfidenz mit Methode und Aufschlüsselung (Summe = Score), mindestens zwei Szenarien mit Niveaus und einen `backtest`-Block. Test je Mustertyp (13 Typen). Die Trefferquote kommt aus `backtest_runs`; solange 3C nicht gelaufen ist, steht dort ausdrücklich "nicht berechnet" |
| 4 Unsicherheit | noch nicht anwendbar | Prognosen folgen in Phase 4 |
| 5 Hinweis auf jeder Seite | unverändert | Frontend-Layout |
| 6 Keine erfundenen Daten | erfüllt | Keine geschätzte Trefferquote; laufende Kerze wird nicht ausgewertet; Volumen-Kriterien entfallen ohne Volumendaten (Gewichte werden sichtbar neu verteilt); leere Antworten nennen den Grund (`empty_reason`: noch nicht ausgeführt, zu wenige Kerzen, keine Intraday-Daten für XETRA, kein Muster erfüllt die Kriterien) |

Offen/ehrlich:
- Parameter (z. B. 1,5 % Abweichung der Tiefs, ATR-Faktor 2, Gewichte der Kriterien) sind begründete Festlegungen aus der gängigen Literatur, nicht an Daten optimiert. Ob sie sinnvoll trennen, zeigt erst der Backtest (3C).
- Getestet mit synthetischen Kursreihen bekannten Ergebnisses und einer zufälligen Reihe (Laufzeit ca. 0,2 s für 1.300 Kerzen), nicht mit echten Kursdaten.
- Mehrere Deutungen derselben Kursbewegung sind möglich (z. B. Doppelboden und Dreieck über denselben Wendepunkten); beide werden mit eigener Begründung gezeigt. Innerhalb einer Musterfamilie bleibt bei Überlappung nur die Erkennung mit der höchsten Konfidenz.
- Erkennungen am rechten Rand können sich mit neuen Kerzen ändern (z. B. ein Dreieck bekommt einen weiteren Wendepunkt); sie werden dann neu berechnet und erhalten eine neue ID.

## Phase 3C (Muster-Backtest)

| Regel | Stand | Beleg |
|---|---|---|
| 1 Keine Empfehlungssprache | erfüllt | `test_grundregeln.py` läuft über den neuen Code. Ergebnistexte beschreiben nur Anteile ("In 35,3 % von 17 in Echtzeit erkannten Fällen wurde das Muster bestätigt", "Das 95-%-Intervall überdeckt die Basisrate"); keine Handlungsaufforderung |
| 2 Quellentransparenz | erfüllt | Jeder Lauf speichert Quelle (Name, Link, Nutzungsbedingungen, Verzögerung), Abrufzeitraum, Zeitraum der Kerzen, verwendete und fehlende Werte mit Grund; die API liefert `source`, `method`, `universe`, `date_range`; das Panel zeigt sie unter "Wie wurde das berechnet?" |
| 3 Erklärpflicht | erfüllt, sobald der Job mit echten Daten gelaufen ist | Trefferquote, Stichprobengröße, 95-%-Intervall, Basisrate, mittlere Veränderung und Szenario-Anteile je Mustertyp; "Historisch nicht besser als Zufall" auch dann, wenn die Quote unter der Basisrate liegt |
| 4 Unsicherheit | erfüllt (für Muster) | Wilson-Intervall, Hinweis auf kleine Stichprobe (unter 30), Hinweis auf nicht unabhängige Fälle und Survivorship Bias |
| 5 Hinweis auf jeder Seite | unverändert | Frontend-Layout |
| 6 Keine erfundenen Daten | erfüllt | Der Job speichert nur, was eine echte Kursquelle geliefert hat, und bricht ohne Daten ohne Speichern ab (`test_job_without_data_stores_nothing`). Ohne Fälle bleibt die Quote `null`. Die laufende Tageskerze wird nicht verwendet. Tests nutzen synthetische Reihen nur in der Testdatenbank |

Offen/ehrlich:
- Noch nicht mit echten Daten gelaufen (hier gibt es keinen Stooq-Schlüssel). Bis Luca den Job startet, zeigt das Dashboard weiter "nicht berechnet".
- Treffer-Definition (5 % in 20 Kerzen) und Parameter der Mustererkennung sind Festlegungen, nicht an Daten optimiert. Wer sie nach dem Ergebnis verändert, riskiert eine Überanpassung.
- Ob Stooq Splits und Dividenden bereinigt, ist nicht geprüft; Sprünge über 40 % werden deshalb ausgeschlossen und gezählt.
- Schrittweite 5 Kerzen: Ein Fall kann bis zu 4 Kerzen später beginnen als bei täglicher Auswertung (nie früher). `--step 1` ist genauer, aber ca. fünfmal langsamer.
## Fix: Backtest und Tagesdaten mit Yahoo, wenn Stooq fehlt

| Regel | Stand | Beleg |
|---|---|---|
| 1 Keine Empfehlungssprache | erfüllt | Neue Texte nennen nur Quelle und fehlende Einrichtung; `test_grundregeln.py` läuft darüber |
| 2 Quellentransparenz | erfüllt | Ein Backtest-Lauf nutzt genau eine Quelle, gespeichert in `metrics.source` und im Text "Tagesdaten von …"; die Musteransicht zeigt "Yahoo Finance (inoffiziell)" (`test_backtest_with_yahoo_records_yahoo_as_source`). Yahoo erscheint auf der Seite Quellen als inoffiziell mit Nutzungsbedingungen |
| 3 Erklärpflicht | unverändert | |
| 4 Unsicherheit | unverändert | |
| 5 Hinweis auf jeder Seite | unverändert | |
| 6 Keine erfundenen Daten | erfüllt | Ohne eingerichtete Quelle bricht der Job mit Hinweis ab (`test_job_refuses_without_any_daily_source`). Yahoo-Tage mit fehlenden Werten werden ausgelassen, HTML- oder Fehlerantworten werden nie als Kurse gelesen (`test_yahoo_unknown_symbol_is_empty_and_bad_answers_are_errors`) |

Offen/ehrlich:
- Der Yahoo-Abruf ist nur gegen nachgebaute Antworten getestet; aus dieser Umgebung ist Yahoo nicht erreichbar. Der erste echte Lauf bei Luca zeigt, ob der Endpunkt ohne Anmeldung liefert.
- Yahoo-Kurse sind splitbereinigt, nicht dividendenbereinigt. Ergebnisse aus Stooq und Yahoo sind deshalb nicht exakt vergleichbar; jeder Lauf nennt seine Quelle.

## Phase 4A (Prognosen, Szenarien, Prognose-Backtest, Backend)

| Regel | Stand | Beleg |
|---|---|---|
| 1 Keine Empfehlungssprache | erfüllt | `test_grundregeln.py` läuft über den neuen Code. Texte beschreiben nur Anteile simulierter Pfade und Fehlermaße ("schließt zuerst über 151,40"); keine Kursziele, kein Einzelwert als Erwartung |
| 2 Quellentransparenz | erfüllt | Jede Prognose speichert `source_ids`, `fetched_at`, Zeitraum und Kerzenanzahl; die API liefert `data_basis` mit Quellen. Backtest-Läufe speichern Zeitraum, Instrument, Parameter und `source_ids` |
| 3 Erklärpflicht | unverändert, ergänzt | Muster-Szenarien zeigen zusätzlich den simulierten Anteil neben der historischen Quote aus dem Muster-Backtest, mit dem Hinweis, dass die Simulation das Muster nicht kennt |
| 4 Unsicherheit | erfüllt (Backend) | Die API liefert nur Quantile je Schritt (Bänder 50/80/95 %), keinen Linien-Endpunkt. Methode mit Annahmen und Grenzen (`/forecasts/methods`), Abdeckung, Median-Fehler und Pinball-Verlust gegen "Kurs bleibt gleich", Diebold-Mariano-p-Wert und ein offenes Urteil, wenn das Modell nicht besser ist (Tests `test_backtest_random_walk_is_not_better_than_naive`, `test_backtest_detects_skill_on_predictable_series`) |
| 5 Hinweis auf jeder Seite | unverändert | Frontend-Layout; die API liefert zusätzlich `note` ("keine Vorhersage und keine Anlageberatung") |
| 6 Keine erfundenen Daten | erfüllt | Fehlermaße nur aus einem Backtest auf gespeicherten Kerzen, sonst `"nicht_berechnet"` mit `null`; unter 30 Prüfzeitpunkten kein Urteil (`better_than_naive: null`); die laufende Kerze geht nie ein; veraltete Muster-Wahrscheinlichkeiten werden nicht gezeigt; Demodaten werden als `is_demo` markiert |

Offen/ehrlich:
- Getestet nur mit synthetischen Reihen (Zufallspfade mit festem Seed, AR(1)-Reihen). Echte Abdeckung und Fehlermaße gibt es erst nach einem Lauf mit echten Kursdaten auf Lucas Rechner.
- Auf einem reinen Zufallspfad ist die Hauptmethode beim Median erwartungsgemäß nicht besser als "Kurs bleibt gleich" (Trend wird entfernt). Ihr Nutzen liegt in der Breite der Bänder; das sagt `method_note` offen.
- Parameter (750 Tage Rückblick, Blocklänge 10, 20 Tage Horizont, Prüfzeitpunkt alle 5 Tage) sind übliche Festlegungen, nicht optimiert. ARIMA ist bewusst nur (1,1,0) ohne Ordnungswahl, damit keine zusätzliche Bibliothek (statsmodels) nötig ist.
- Künftige Handelstage sind als Werktage gezählt; Feiertage fehlen. Bei schrägen Musterlinien wird das Niveau der letzten Kerze über den Horizont konstant gehalten.
- Überlappende Horizonte machen die Prüfzeitpunkte abhängig; der Diebold-Mariano-Test berücksichtigt das per Newey-West, das Konfidenzniveau bleibt trotzdem eine Näherung.

## Phase 4B (Frontend: Prognosekorridor, Szenario-Niveaus, Methoden- und Backtest-Panel)

| Regel | Stand | Beleg |
|---|---|---|
| 1 Keine Empfehlungssprache | erfüllt | `test_grundregeln.py` läuft über den neuen Code. Bänder sind einfarbig blau abgestuft, Szenario-Niveaus nur beschriftet ("Bestätigung", "Scheitern"), keine Ampeln, keine Kursziele |
| 2 Quellentransparenz | erfüllt | Das Panel nennt Datenstand, Erstellzeit, Verfahren und Version und zeigt die Kursquellen als `SourceTip` |
| 3 Erklärpflicht | unverändert | Szenario-Niveaus kommen aus `PatternDetection`; der Vergleich mit dem Korridor nennt nur die Lage, keine Wahrscheinlichkeit; simulierte Pfadanteile und historische Quote stehen getrennt und beschriftet nebeneinander |
| 4 Unsicherheit | erfüllt (Anzeige) | Nur Bänder 50/80/95 % (`PriceChart`: verschachtelte Flächen, keine Linie, auch kein Median). Methode, Annahmen, Grenzen, Parameter, Abdeckung, Fehlermaße gegen "Kurs bleibt gleich", Signifikanztest und Ergebnis je Horizont sind einsehbar; "historisch nicht nachweisbar besser" wird offen genannt (`forecast.test.tsx`) |
| 5 Hinweis auf jeder Seite | unverändert | Layout |
| 6 Keine erfundenen Daten | erfüllt | Fehlende Prognose (mit `empty_reason`), unvollständige Schritte (verworfen), fehlender Backtest, nicht-tägliche Kerzen und Demodaten werden ausdrücklich gezeigt; nie Platzhalterwerte |

Offen/ehrlich:
- Gebaut gegen den Vertrag aus dem Branch `phase-4a-forecasts` und mit simulierten Antworten geprüft (Vitest, Sichtprüfung der verschachtelten Bänder im Browser mit Testdaten), nicht gegen das laufende Backend.
- Die Einordnung "nahe am Sollwert" der Abdeckung (Abweichung bis 5 Prozentpunkte) und die Warnschwelle "kleine Stichprobe" (unter 30) sind Annahmen der Oberfläche.
- Die Horizonte 5/10/20 folgen dem Backend-Limit von 20 Kerzen. `GET /forecasts/methods` wird noch nicht genutzt; die Methodenbeschreibung kommt aus der Prognose-Antwort.

## Phase 5B (Tests: Ende-zu-Ende, Muster-Regression)

| Regel | Stand | Beleg |
|---|---|---|
| 1 Keine Empfehlungssprache | zusätzlich geprüft | `e2e/grundregeln.spec.ts` liest den sichtbaren Text jeder Seite und sucht die Wortliste aus `backend/app/grundregeln.py` (einzige Quelle); zusätzlich Panels für Muster und Prognose |
| 2 Quellentransparenz | zusätzlich geprüft | E2E öffnet die Quellenangaben von Kurs, Chart und Meldungen (Anbieter, Verzögerung, Abrufzeit, Nutzungsbedingungen) und prüft die Seite Quellen: Intervall, Verzögerung, Status, Grund bei deaktivierten oder nicht erreichbaren Quellen |
| 3 Erklärpflicht | zusätzlich geprüft | E2E: Name, Lage mit Zeitraum, Kriterientabelle mit Werten, Konfidenz samt Berechnung, mindestens zwei Szenarien, beide Niveaus, Backtest mit Stichprobe. Regressionstest: jede Erkennung jedes Fixtures erfüllt die Erklärpflicht |
| 4 Unsicherheit | zusätzlich geprüft | E2E: Legende 50/80/95 %, Methode, Abdeckung und Fehlermaße gegen "Kurs bleibt gleich" |
| 5 Hinweis auf jeder Seite | automatisiert | E2E prüft auf Anmeldung, Watchlist, Chart, Nachrichten, Quellen und unbekannter Seite den exakten Wortlaut; entfernt man den Hinweis, schlägt der Test fehl (ausprobiert) |
| 6 Keine erfundenen Daten | erfüllt | E2E-Daten sind nur mit `DEMO_MODE=true` anlegbar, heißen "Beispieldaten", tragen `is_demo` und zeigen das Banner; keine Anbieter-Zugriffe im Testlauf |

Offen/ehrlich:
- Die Testdaten und der Muster-Backtest in den E2E-Läufen sind erfundene Beispielwerte; sie prüfen die Darstellung, nicht die Qualität der Erkennung oder der Prognose.
- Das Zeichnen im Chart (Canvas) prüft kein Test inhaltlich, nur dass es gerendert wird; Muster-Markierungen und Korridor-Flächen bleiben eine Sichtprüfung.
- Die Golden-Datei hält den heutigen Stand der (unabgestimmten) Standardparameter fest. Sie sagt "unverändert", nicht "richtig".
- Beim Schreiben der Tests fielen drei Fehler auf und wurden behoben: Abmelden hatte keine Wirkung (`qc.clear()` entfernte die Abfrage "me"), jede Zugriffszeile im uvicorn-Log scheiterte an der Log-Bereinigung, und eine neu hinzugefügte Aktie zeigte bis zum nächsten Abruf "0 Muster".

Erklärtexte (KI, Punkt 6 der Spezifikation): Regel 1 wird zur Laufzeit erzwungen (`explain_facts.validate`: Wortliste aus `grundregeln.py` plus Wendungen wie "empfehlen"; bei Treffer gilt die Vorlage). Regel 3/4: der Text nennt nur Werte der Erkennung bzw. Prognose; jede Zahl und jedes Datum wird gegen die Werte geprüft, Trefferquote fehlt = der Text sagt das. Regel 6: keine KI-Texte für Demodaten; KI-Text und Vorlage sind getrennt gekennzeichnet (Tests `test_explanations.py`, `aiExplanation.test.tsx`, E2E `patterns.spec.ts`). Offen: ob die Texte für Laien verständlich sind, ist mit echtem Schlüssel noch nicht beurteilt.
