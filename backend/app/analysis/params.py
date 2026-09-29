"""Dokumentierte Parameter der Mustererkennung. Jede Erkennung speichert die verwendeten Werte, ihren Hash
und ALGO_VERSION, damit sie reproduzierbar ist. Änderungen an Regeln erhöhen ALGO_VERSION."""
import hashlib
import json
from dataclasses import dataclass
from typing import Any

ALGO_VERSION = "1.0.0"


@dataclass(frozen=True)
class Param:
    value: float
    unit: str
    description: str


PARAM_DOCS: dict[str, dict[str, Param]] = {
    "pivots": {
        "atr_periode": Param(14, "Kerzen", "Periode der ATR (Average True Range nach Wilder)"),
        "atr_faktor": Param(2.0, "Faktor", "Ein Wendepunkt steht fest, wenn der Kurs sich um mindestens so viele ATR "
                            "davon entfernt hat"),
        "min_bewegung_pct": Param(1.0, "%", "Mindestbewegung für einen Wendepunkt, falls größer als die ATR-Schwelle"),
    },
    "status": {
        "invalidierung_puffer_pct": Param(1.5, "%", "Abstand jenseits des Extrempunkts, ab dem ein Muster "
                                          "als ungültig gilt (Doppel- und Kopf-Schulter-Muster)"),
        "frist_min_kerzen": Param(10, "Kerzen", "Mindestfrist für Bestätigung nach Musterende"),
        "frist_max_kerzen": Param(60, "Kerzen", "Höchstfrist für Bestätigung nach Musterende; sonst Musterbreite"),
    },
    "doppel": {
        "max_extrem_abweichung_pct": Param(1.5, "%", "Höchstabweichung der beiden Hochs bzw. Tiefs (Idealwert 0 %)"),
        "min_abstand_kerzen": Param(10, "Kerzen", "Mindestabstand zwischen den beiden Extrempunkten"),
        "max_abstand_kerzen": Param(120, "Kerzen", "Höchstabstand zwischen den beiden Extrempunkten"),
        "ideal_abstand_min": Param(20, "Kerzen", "Abstand ab dem der Teilwert 1 ist"),
        "ideal_abstand_max": Param(80, "Kerzen", "Abstand bis zu dem der Teilwert 1 ist"),
        "min_tiefe_pct": Param(3.0, "%", "Mindestabstand des Zwischenhochs/-tiefs vom näheren Extrempunkt"),
        "ideal_tiefe_pct": Param(8.0, "%", "Tiefe, ab der der Teilwert 1 ist"),
        "min_vortrend_pct": Param(5.0, "%", "Mindestbewegung vom vorherigen Wendepunkt zum ersten Extrempunkt"),
        "ideal_vortrend_pct": Param(15.0, "%", "Vortrend, ab dem der Teilwert 1 ist"),
    },
    "kopf_schulter": {
        "min_kopf_ueberhang_pct": Param(2.0, "%", "Kopf liegt mindestens so weit jenseits der höheren Schulter"),
        "ideal_kopf_ueberhang_pct": Param(6.0, "%", "Überhang, ab dem der Teilwert 1 ist"),
        "max_schulter_abweichung_pct": Param(5.0, "%", "Höchstabweichung der beiden Schultern (Idealwert 0 %)"),
        "max_nacken_neigung_pct": Param(5.0, "%", "Höchstunterschied der beiden Nackenpunkte (Idealwert 0 %)"),
        "min_zeit_verhaeltnis": Param(0.5, "Faktor", "Dauer linke Seite / rechte Seite mindestens"),
        "max_zeit_verhaeltnis": Param(2.0, "Faktor", "Dauer linke Seite / rechte Seite höchstens (Idealwert 1)"),
        "min_breite_kerzen": Param(15, "Kerzen", "Mindestbreite von linker bis rechter Schulter"),
        "max_breite_kerzen": Param(250, "Kerzen", "Höchstbreite von linker bis rechter Schulter"),
        "min_vortrend_pct": Param(5.0, "%", "Mindestbewegung vom vorherigen Wendepunkt zur linken Schulter"),
        "ideal_vortrend_pct": Param(15.0, "%", "Vortrend, ab dem der Teilwert 1 ist"),
    },
    "dreieck_keil": {
        "min_pivots": Param(4, "Anzahl", "Mindestzahl Wendepunkte (je mindestens 2 an jeder Linie)"),
        "max_pivots": Param(6, "Anzahl", "Höchstzahl Wendepunkte je Kandidat"),
        "min_breite_kerzen": Param(15, "Kerzen", "Mindestdauer"),
        "max_breite_kerzen": Param(150, "Kerzen", "Höchstdauer"),
        "flach_steigung_pct": Param(0.05, "% je Kerze", "Eine Linie gilt als waagerecht bis zu dieser Steigung"),
        "min_steigung_pct": Param(0.05, "% je Kerze", "Eine Linie gilt als steigend/fallend ab dieser Steigung"),
        "max_anpassung_pct": Param(1.5, "%", "Höchstabstand eines Wendepunkts von seiner Linie"),
        "min_verengung_pct": Param(20.0, "%", "Mindestverengung der Spanne vom Anfang zum Ende"),
        "ideal_verengung_pct": Param(50.0, "%", "Verengung, ab der der Teilwert 1 ist"),
        "toleranz_atr": Param(0.5, "Faktor", "Toleranz um die Linien für Schlusskurse innerhalb, in ATR"),
        "min_anteil_innerhalb_pct": Param(90.0, "%", "Mindestanteil der Schlusskurse zwischen den Linien"),
    },
    "flagge": {
        "min_stange_pct": Param(8.0, "%", "Mindestbewegung der Fahnenstange"),
        "ideal_stange_pct": Param(15.0, "%", "Fahnenstange, ab der der Teilwert 1 ist"),
        "min_stange_kerzen": Param(3, "Kerzen", "Mindestdauer der Fahnenstange"),
        "max_stange_kerzen": Param(15, "Kerzen", "Höchstdauer der Fahnenstange"),
        "min_flagge_kerzen": Param(5, "Kerzen", "Mindestdauer der Konsolidierung"),
        "max_flagge_kerzen": Param(20, "Kerzen", "Höchstdauer der Konsolidierung"),
        "max_ruecksetzer_pct": Param(50.0, "%", "Höchster Rücksetzer in der Konsolidierung, in % der Fahnenstange"),
        "ideal_ruecksetzer_pct": Param(25.0, "%", "Rücksetzer, bis zu dem der Teilwert 1 ist"),
        "max_parallel_abweichung_pct": Param(0.15, "% je Kerze", "Flagge: Höchstunterschied der Steigungen"),
        "max_gegen_steigung_pct": Param(0.05, "% je Kerze", "Flagge: Mittellinie höchstens so steil in Richtung "
                                        "der Fahnenstange (sonst keine Konsolidierung)"),
        "max_neigung_anteil_pct": Param(40.0, "%", "Steigung der Kanal-Mitte höchstens dieser Anteil der mittleren "
                                        "Steigung der Fahnenstange (sonst eher Trendwende als Konsolidierung)"),
        "wimpel_min_steigung_pct": Param(0.02, "% je Kerze", "Wimpel: obere Linie fällt und untere steigt je "
                                         "mindestens so stark"),
        "toleranz_atr": Param(0.5, "Faktor", "Toleranz um die Kanal-Linien für Schlusskurse, in ATR"),
        "min_anteil_innerhalb_pct": Param(90.0, "%", "Mindestanteil der Schlusskurse im Kanal"),
        "ausbruch_frist_kerzen": Param(10, "Kerzen", "Frist für den Ausbruch nach Ende der Konsolidierung"),
    },
    "volumen": {
        "ideal_verhaeltnis": Param(0.7, "Faktor", "Volumenverhältnis (später/früher), bis zu dem der Teilwert 1 ist"),
        "grenz_verhaeltnis": Param(1.3, "Faktor", "Volumenverhältnis, ab dem der Teilwert 0 ist"),
        "fenster_kerzen": Param(2, "Kerzen", "Kerzen links und rechts eines Wendepunkts für das mittlere Volumen"),
    },
    "zonen": {
        "rueckblick_kerzen": Param(500, "Kerzen", "Nur Wendepunkte aus diesem Zeitraum bilden Zonen"),
        "toleranz_atr": Param(0.5, "Faktor", "Zonenbreite als Vielfaches der mittleren ATR"),
        "min_toleranz_pct": Param(0.75, "%", "Mindest-Zonenbreite in % des letzten Schlusskurses"),
        "min_beruehrungen": Param(3, "Anzahl", "Mindestzahl Wendepunkte in der Zone"),
        "ideal_beruehrungen": Param(6, "Anzahl", "Berührungen, ab denen der Teilwert 1 ist"),
        "min_zeitspanne_kerzen": Param(20, "Kerzen", "Mindestabstand zwischen erster und letzter Berührung"),
        "ideal_zeitspanne_kerzen": Param(120, "Kerzen", "Zeitspanne, ab der der Teilwert 1 ist"),
        "ideal_aktualitaet_kerzen": Param(20, "Kerzen", "Letzte Berührung höchstens so lange her: Teilwert 1"),
        "max_aktualitaet_kerzen": Param(250, "Kerzen", "Letzte Berührung so lange her: Teilwert 0"),
        "max_zonen": Param(8, "Anzahl", "Höchstzahl angezeigter Zonen (die mit der höchsten Konfidenz)"),
    },
}

Params = dict[str, dict[str, float]]


def default_params() -> Params:
    return {group: {k: p.value for k, p in items.items()} for group, items in PARAM_DOCS.items()}


def params_hash(params: Params) -> str:
    blob = json.dumps({"v": ALGO_VERSION, "p": params}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:8]


def params_doc(groups: list[str], params: Params) -> list[dict[str, Any]]:
    """Parameter mit Beschreibung für /patterns/catalog (tatsächlich verwendete Werte)."""
    return [
        {"key": f"{g}.{k}", "value": params[g][k], "unit": p.unit, "description": p.description}
        for g in groups for k, p in PARAM_DOCS[g].items()
    ]


def subset(groups: list[str], params: Params) -> dict[str, float]:
    return {f"{g}.{k}": v for g in groups for k, v in params[g].items()}
