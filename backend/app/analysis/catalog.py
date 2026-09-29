"""Beschreibung aller Mustertypen für /patterns/catalog ("Wie wird das berechnet?")."""
from typing import Any

from app.analysis.params import ALGO_VERSION, Params, params_doc
from app.analysis.patterns import double, flags, head_shoulders, triangles

_DOUBLE = [
    ("extrem_abweichung", "Abweichung der beiden Extrempunkte", "höchstens doppel.max_extrem_abweichung_pct", True),
    ("tiefe", "Abstand des Zwischenpunkts", "mindestens doppel.min_tiefe_pct", True),
    ("abstand", "Abstand der Extrempunkte", "zwischen doppel.min_abstand_kerzen und doppel.max_abstand_kerzen", True),
    ("vortrend", "Vorheriger Trend", "mindestens doppel.min_vortrend_pct", True),
    ("volumen", "Volumen am zweiten Extrempunkt", "niedriger als am ersten (nur mit Volumendaten)", False),
]
_HS = [
    ("kopf_ueberhang", "Kopf gegenüber den Schultern", "mindestens kopf_schulter.min_kopf_ueberhang_pct", True),
    ("schulter_abweichung", "Symmetrie der Schultern", "höchstens kopf_schulter.max_schulter_abweichung_pct", True),
    ("nacken_neigung", "Neigung der Nackenlinie", "höchstens kopf_schulter.max_nacken_neigung_pct", True),
    ("zeit_symmetrie", "Zeitliche Symmetrie", "Verhältnis zwischen kopf_schulter.min_zeit_verhaeltnis und "
     "kopf_schulter.max_zeit_verhaeltnis", True),
    ("vortrend", "Vorheriger Trend", "mindestens kopf_schulter.min_vortrend_pct", True),
    ("volumen", "Volumen an der rechten Schulter", "niedriger als am Kopf (nur mit Volumendaten)", False),
]
_TRI = [
    ("form", "Verlauf der Linien", "Steigungen gemäß Mustertyp (dreieck_keil.flach_steigung_pct, "
     "dreieck_keil.min_steigung_pct)", True),
    ("verengung", "Verengung der Spanne", "mindestens dreieck_keil.min_verengung_pct", True),
    ("anpassung", "Lage der Wendepunkte an den Linien", "höchstens dreieck_keil.max_anpassung_pct", True),
    ("beruehrungen", "Berührungen je Linie", "mindestens 2", True),
    ("innerhalb", "Schlusskurse zwischen den Linien", "mindestens dreieck_keil.min_anteil_innerhalb_pct", True),
    ("volumen", "Volumenverlauf", "zweite Hälfte niedriger als erste (nur mit Volumendaten)", False),
]
_FLAG = [
    ("stange", "Fahnenstange", "mindestens flagge.min_stange_pct in höchstens flagge.max_stange_kerzen", True),
    ("ruecksetzer", "Rücksetzer in der Konsolidierung", "höchstens flagge.max_ruecksetzer_pct", True),
    ("neigung", "Neigung der Konsolidierung", "höchstens flagge.max_neigung_anteil_pct der Fahnenstange", True),
    ("form", "Form des Kanals", "Flagge: parallel (flagge.max_parallel_abweichung_pct); Wimpel: zusammenlaufend "
     "(flagge.wimpel_min_steigung_pct)", True),
    ("innerhalb", "Schlusskurse im Kanal", "mindestens flagge.min_anteil_innerhalb_pct", True),
    ("dauer", "Dauer der Konsolidierung", "flagge.min_flagge_kerzen bis flagge.max_flagge_kerzen", True),
    ("volumen", "Volumen in der Konsolidierung", "niedriger als in der Fahnenstange (nur mit Volumendaten)", False),
]

_GROUPS = {"doppel": ["pivots", "status", "doppel", "volumen"],
           "kopf_schulter": ["pivots", "status", "kopf_schulter", "volumen"],
           "dreieck_keil": ["pivots", "status", "dreieck_keil", "volumen"], "flagge": ["flagge", "volumen"]}

ENTRIES: list[tuple[str, str, str, str, str, list[tuple[str, str, str, bool]], dict[str, float]]] = [
    ("doppelboden", "Doppelboden", "aufwärts", "doppel",
     "Zwei ähnlich tiefe Tiefs mit einem Zwischenhoch nach einem Rückgang. Bestätigt, wenn ein Schlusskurs über "
     "dem Zwischenhoch (Nackenlinie) liegt.", _DOUBLE, double.WEIGHTS),
    ("doppelhoch", "Doppelhoch", "abwärts", "doppel",
     "Zwei ähnlich hohe Hochs mit einem Zwischentief nach einem Anstieg. Bestätigt, wenn ein Schlusskurs unter "
     "dem Zwischentief (Nackenlinie) liegt.", _DOUBLE, double.WEIGHTS),
    ("kopf_schulter", "Kopf-Schulter-Formation", "abwärts", "kopf_schulter",
     "Drei Hochs, das mittlere (Kopf) am höchsten, die äußeren (Schultern) ähnlich hoch. Bestätigt bei einem "
     "Schlusskurs unter der Nackenlinie durch die beiden Zwischentiefs.", _HS, head_shoulders.WEIGHTS),
    ("kopf_schulter_invers", "Inverse Kopf-Schulter-Formation", "aufwärts", "kopf_schulter",
     "Spiegelbild der Kopf-Schulter-Formation mit drei Tiefs. Bestätigt bei einem Schlusskurs über der "
     "Nackenlinie.", _HS, head_shoulders.WEIGHTS),
    ("dreieck_aufsteigend", "Aufsteigendes Dreieck", "aufwärts", "dreieck_keil",
     "Waagerechte obere Linie, steigende untere Linie. Bestätigt bei einem Schlusskurs über der oberen Linie.",
     _TRI, triangles.WEIGHTS),
    ("dreieck_absteigend", "Absteigendes Dreieck", "abwärts", "dreieck_keil",
     "Waagerechte untere Linie, fallende obere Linie. Bestätigt bei einem Schlusskurs unter der unteren Linie.",
     _TRI, triangles.WEIGHTS),
    ("dreieck_symmetrisch", "Symmetrisches Dreieck", "offen", "dreieck_keil",
     "Fallende obere und steigende untere Linie. Die Richtung ergibt sich erst aus dem Ausbruch (Schlusskurs "
     "außerhalb einer der Linien).", _TRI, triangles.WEIGHTS),
    ("keil_steigend", "Steigender Keil", "abwärts", "dreieck_keil",
     "Beide Linien steigen, die untere steiler, die Spanne verengt sich. Bestätigt bei einem Schlusskurs unter "
     "der unteren Linie.", _TRI, triangles.WEIGHTS),
    ("keil_fallend", "Fallender Keil", "aufwärts", "dreieck_keil",
     "Beide Linien fallen, die obere steiler, die Spanne verengt sich. Bestätigt bei einem Schlusskurs über der "
     "oberen Linie.", _TRI, triangles.WEIGHTS),
    ("flagge_aufwaerts", "Flagge nach Anstieg", "aufwärts", "flagge",
     "Steiler Anstieg (Fahnenstange), danach ein schmaler, waagerechter oder leicht fallender Kanal. Bestätigt "
     "bei einem Schlusskurs über der oberen Kanal-Linie.", _FLAG, flags.WEIGHTS),
    ("flagge_abwaerts", "Flagge nach Rückgang", "abwärts", "flagge",
     "Steiler Rückgang, danach ein schmaler, waagerechter oder leicht steigender Kanal. Bestätigt bei einem "
     "Schlusskurs unter der unteren Kanal-Linie.", _FLAG, flags.WEIGHTS),
    ("wimpel_aufwaerts", "Wimpel nach Anstieg", "aufwärts", "flagge",
     "Steiler Anstieg, danach zusammenlaufende Linien. Bestätigt bei einem Schlusskurs über der oberen Linie.",
     _FLAG, flags.WEIGHTS),
    ("wimpel_abwaerts", "Wimpel nach Rückgang", "abwärts", "flagge",
     "Steiler Rückgang, danach zusammenlaufende Linien. Bestätigt bei einem Schlusskurs unter der unteren Linie.",
     _FLAG, flags.WEIGHTS),
]

PATTERN_NAMES = {e[0]: e[1] for e in ENTRIES}


def catalog(params: Params) -> list[dict[str, Any]]:
    out = []
    for ptype, name, direction, group, description, crits, weights in ENTRIES:
        out.append({
            "pattern_type": ptype, "name": name, "direction_if_confirmed": direction, "description": description,
            "criteria": [{"key": k, "name": n, "rule": r, "required": req, "weight": weights[k]}
                         for k, n, r, req in crits],
            "params": params_doc(_GROUPS[group], params), "algo_version": ALGO_VERSION,
        })
    return out
