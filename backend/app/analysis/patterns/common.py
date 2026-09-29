"""Gemeinsame Bausteine der Muster: Datenklassen, Teilwert-Funktionen, Konfidenz, Status, Erklärtext.

Konfidenz: gewichteter Mittelwert der Teilwerte (0 bis 1) aller bewerteten Kriterien. Ein Teilwert ist 1
beim Idealwert und fällt linear bis 0 an der Grenze des Kriteriums. Fehlt eine Angabe (z. B. Volumen),
wird das Kriterium nicht bewertet und die übrigen Gewichte werden auf die Summe 1 hochgerechnet."""
import math
from dataclasses import dataclass, field
from typing import Literal

from app.analysis import fmt
from app.analysis.params import Params
from app.analysis.pivots import Pivot
from app.analysis.series import Bars, FloatArray, mean_volume

Direction = Literal["aufwärts", "abwärts", "offen"]
Status = Literal["in_bildung", "bestaetigt", "ungueltig"]

STATUS_LABELS: dict[str, str] = {"in_bildung": "In Bildung", "bestaetigt": "Bestätigt", "ungueltig": "Ungültig"}

CONFIDENCE_METHOD = (
    "Gewichteter Mittelwert der Teilwerte (0 bis 1) aller Kriterien. Ein Teilwert ist 1 beim Idealwert und "
    "fällt linear bis 0 an der Grenze des Kriteriums. Nicht bewertbare Kriterien (z. B. fehlendes Volumen) "
    "entfallen, die übrigen Gewichte werden auf die Summe 1 hochgerechnet."
)


@dataclass(frozen=True)
class Context:
    bars: Bars
    atr: FloatArray
    pivots: list[Pivot]
    params: Params
    timeframe: str

    def date(self, idx: int) -> str:
        return fmt.stamp(self.bars.ts[idx], self.timeframe)


@dataclass(frozen=True)
class KeyPoint:
    role: str
    label: str
    idx: int
    price: float


@dataclass(frozen=True)
class Line:
    """Gerade durch (i0, p0) und (i1, p1); waagerecht, wenn p0 == p1."""
    role: str
    label: str
    i0: int
    p0: float
    i1: int
    p1: float
    extend_right: bool = True

    @property
    def slope(self) -> float:
        return 0.0 if self.i1 == self.i0 else (self.p1 - self.p0) / (self.i1 - self.i0)

    def at(self, i: int) -> float:
        return self.p0 + self.slope * (i - self.i0)

    @classmethod
    def horizontal(cls, role: str, label: str, i0: int, i1: int, price: float) -> "Line":
        return cls(role, label, i0, price, i1, price)


@dataclass
class Criterion:
    key: str
    name: str
    rule: str
    threshold: float | None
    actual: float | None
    unit: str
    actual_text: str
    required: bool
    passed: bool
    sub_score: float
    weight: float


@dataclass
class Scenario:
    kind: str  # bestaetigung | scheitern | ausbruch_oben | ausbruch_unten
    title: str
    trigger_level: float
    trigger_rule: str
    description: str


@dataclass
class Detection:
    pattern_type: str
    name: str
    direction: Direction
    start_idx: int
    end_idx: int
    formed_idx: int  # letzte Kerze, deren Daten in die Erkennung eingehen (für Backtests ohne Vorgriff)
    key_points: list[KeyPoint]
    lines: list[Line]
    criteria: list[Criterion]
    confirmation: Line
    invalidation: Line
    deadline_idx: int  # ohne Bestätigung bis hier: ungültig
    apex_idx: int | None = None  # Dreiecke/Keile: Spitze erreicht ohne Ausbruch = ungültig
    # vom Status-Schritt gesetzt
    status: Status = "in_bildung"
    status_reason: str = ""
    status_idx: int | None = None
    confirmed_idx: int | None = None
    invalidated_idx: int | None = None
    breakout_direction: Direction | None = None
    confirmation_level: float = 0.0
    invalidation_level: float = 0.0
    scenarios: list[Scenario] = field(default_factory=list)
    confidence: float = 0.0
    breakdown: list[dict[str, float | str]] = field(default_factory=list)
    explanation: str = ""
    family: str = ""


# ---------- Teilwerte ----------

def score_le(x: float, ideal: float, limit: float) -> float:
    """Kleiner ist besser: 1 bei x <= ideal, 0 bei x >= limit, dazwischen linear."""
    if x <= ideal:
        return 1.0
    if x >= limit or limit == ideal:
        return 0.0
    return round((limit - x) / (limit - ideal), 4)


def score_ge(x: float, ideal: float, limit: float) -> float:
    """Größer ist besser: 1 bei x >= ideal, 0 bei x <= limit, dazwischen linear."""
    if x >= ideal:
        return 1.0
    if x <= limit or limit == ideal:
        return 0.0
    return round((x - limit) / (ideal - limit), 4)


def score_band(x: float, ideal_lo: float, ideal_hi: float, limit_lo: float, limit_hi: float) -> float:
    if x < ideal_lo:
        return score_ge(x, ideal_lo, limit_lo)
    if x > ideal_hi:
        return score_le(x, ideal_hi, limit_hi)
    return 1.0


def crit_le(key: str, name: str, rule: str, actual: float, threshold: float, ideal: float, unit: str,
            actual_text: str, weight: float, required: bool = True) -> Criterion:
    return Criterion(key, name, rule, threshold, round(actual, 4), unit, actual_text, required,
                     actual <= threshold, score_le(actual, ideal, threshold), weight)


def crit_ge(key: str, name: str, rule: str, actual: float, threshold: float, ideal: float, unit: str,
            actual_text: str, weight: float, required: bool = True) -> Criterion:
    return Criterion(key, name, rule, threshold, round(actual, 4), unit, actual_text, required,
                     actual >= threshold, score_ge(actual, ideal, threshold), weight)


def pct_diff(a: float, b: float) -> float:
    """Abweichung in % bezogen auf den kleineren Wert."""
    return abs(a - b) / min(abs(a), abs(b)) * 100.0


def volume_ratio_criterion(ctx: Context, key: str, name: str, rule: str, later: tuple[int, int],
                           earlier: tuple[int, int], later_label: str, earlier_label: str,
                           weight: float) -> Criterion | None:
    """Qualitätskriterium: Volumen im späteren Abschnitt kleiner als im früheren. None ohne Volumendaten."""
    if not ctx.bars.has_volume:
        return None
    v_late = mean_volume(ctx.bars, *later)
    v_early = mean_volume(ctx.bars, *earlier)
    if not (math.isfinite(v_late) and math.isfinite(v_early)) or v_early <= 0:
        return None
    p = ctx.params["volumen"]
    ratio = v_late / v_early
    text = (f"Mittleres Volumen {later_label}: {fmt.num(v_late, 0)}, {earlier_label}: {fmt.num(v_early, 0)}, "
            f"Verhältnis {fmt.num(ratio)}")
    return Criterion(key, name, rule, 1.0, round(ratio, 4), "Faktor", text, False, ratio < 1.0,
                     score_le(ratio, p["ideal_verhaeltnis"], p["grenz_verhaeltnis"]), weight)


def around(ctx: Context, idx: int) -> tuple[int, int]:
    w = int(ctx.params["volumen"]["fenster_kerzen"])
    return idx - w, idx + w


def all_required_pass(criteria: list[Criterion]) -> bool:
    return all(c.passed for c in criteria if c.required)


def deadline(ctx: Context, start: int, end: int) -> int:
    p = ctx.params["status"]
    width = end - start
    return end + int(min(max(width, p["frist_min_kerzen"]), p["frist_max_kerzen"]))


# ---------- Konfidenz, Status, Szenarien, Text ----------

def apply_confidence(det: Detection) -> None:
    total = sum(c.weight for c in det.criteria)
    breakdown: list[dict[str, float | str]] = []
    score = 0.0
    for c in det.criteria:
        w = c.weight / total if total else 0.0
        contribution = w * c.sub_score
        score += contribution
        breakdown.append({"key": c.key, "name": c.name, "weight": round(w, 4), "sub_score": round(c.sub_score, 4),
                          "contribution": round(contribution, 4)})
    det.confidence = round(score, 4)
    det.breakdown = breakdown


def evaluate_status(ctx: Context, det: Detection) -> None:
    """Geht die Kerzen nach dem Musterende durch. Es zählt das zuerst eingetretene Ereignis (per Schlusskurs).
    Nach einer Bestätigung wird `invalidated_idx` noch gesetzt, wenn der Kurs später das beim Bestätigen
    gültige Ungültigkeitsniveau überschreitet; der Status bleibt dann 'bestaetigt'."""
    close = ctx.bars.close
    n = len(ctx.bars)
    up = det.direction == "aufwärts"
    frozen_inv: float | None = None
    for t in range(det.end_idx + 1, n):
        c = float(close[t])
        if det.confirmed_idx is None:
            conf, inv = det.confirmation.at(t), det.invalidation.at(t)
            if det.direction == "offen":
                if c > conf:
                    det.confirmed_idx, det.breakout_direction = t, "aufwärts"
                elif c < inv:
                    det.confirmed_idx, det.breakout_direction = t, "abwärts"
            elif (up and c > conf) or (not up and c < conf):
                det.confirmed_idx = t
            elif (up and c < inv) or (not up and c > inv):
                det.invalidated_idx = t
                det.status, det.status_idx = "ungueltig", t
                det.status_reason = f"Schlusskurs {fmt.price(c)} am {ctx.date(t)} jenseits des Ungültigkeitsniveaus " \
                                    f"{fmt.price(inv)}"
                return
            if det.confirmed_idx is not None:
                det.status, det.status_idx = "bestaetigt", t
                lvl = conf if det.breakout_direction != "abwärts" else inv
                det.status_reason = f"Schlusskurs {fmt.price(c)} am {ctx.date(t)} jenseits des Niveaus {fmt.price(lvl)}"
                if det.direction == "offen":
                    frozen_inv = inv if det.breakout_direction == "aufwärts" else conf
                else:
                    frozen_inv = inv
                continue
            if det.apex_idx is not None and t >= det.apex_idx:
                det.status, det.status_idx, det.invalidated_idx = "ungueltig", t, t
                det.status_reason = f"Spitze der Linien am {ctx.date(t)} erreicht, ohne Ausbruch"
                return
            if t >= det.deadline_idx:
                det.status, det.status_idx, det.invalidated_idx = "ungueltig", t, t
                det.status_reason = f"Keine Bestätigung bis zum Fristende am {ctx.date(t)}"
                return
        else:
            assert frozen_inv is not None
            falls_back = c < frozen_inv if (det.breakout_direction or det.direction) == "aufwärts" else c > frozen_inv
            if falls_back:
                det.invalidated_idx = t
                return
    if det.confirmed_idx is None:
        det.status_reason = "Weder Bestätigungs- noch Ungültigkeitsniveau bisher per Schlusskurs überschritten"


def level_ref_idx(ctx: Context, det: Detection) -> int:
    """Kerze, an der schräge Linien für die Szenario-Niveaus ausgewertet werden."""
    return det.status_idx if det.status_idx is not None else len(ctx.bars) - 1


def build_scenarios(ctx: Context, det: Detection, conf_rule: str, inv_rule: str) -> None:
    ref = level_ref_idx(ctx, det)
    conf, inv = det.confirmation.at(ref), det.invalidation.at(ref)
    det.confirmation_level, det.invalidation_level = round(conf, 4), round(inv, 4)
    when = "" if det.status_idx is None else f" (Wert am {ctx.date(ref)})"
    if det.direction == "offen":
        det.scenarios = [
            Scenario("ausbruch_oben", "Ausbruch nach oben", round(conf, 4),
                     f"Schlusskurs über {conf_rule} bei {fmt.price(conf)}{when}",
                     f"Schließt der Kurs über {fmt.price(conf)}, gilt das Muster „{det.name}“ "
                     "als nach oben aufgelöst."),
            Scenario("ausbruch_unten", "Ausbruch nach unten", round(inv, 4),
                     f"Schlusskurs unter {inv_rule} bei {fmt.price(inv)}{when}",
                     f"Schließt der Kurs unter {fmt.price(inv)}, gilt das Muster „{det.name}“ "
                     "als nach unten aufgelöst."),
        ]
        return
    over, under = ("über", "unter") if det.direction == "aufwärts" else ("unter", "über")
    det.scenarios = [
        Scenario("bestaetigung", "Bestätigung", round(conf, 4),
                 f"Schlusskurs {over} {conf_rule} bei {fmt.price(conf)}{when}",
                 f"Schließt der Kurs {over} {fmt.price(conf)}, gilt das Muster „{det.name}“ als bestätigt. "
                 "Wie es historisch danach weiterging, zeigt der Backtest."),
        Scenario("scheitern", "Scheitern", round(inv, 4),
                 f"Schlusskurs {under} {inv_rule} bei {fmt.price(inv)}{when}",
                 f"Schließt der Kurs {under} {fmt.price(inv)}, bevor das Bestätigungsniveau erreicht ist, "
                 "gilt das Muster als ungültig."),
    ]


def build_explanation(ctx: Context, det: Detection) -> None:
    parts = [f"{det.name} von {ctx.date(det.start_idx)} bis {ctx.date(det.end_idx)}."]
    parts += [c.actual_text + "." for c in det.criteria if c.required]
    parts.append(f"Konfidenz der Erkennung: {fmt.pct(det.confidence * 100, 0)} "
                 "(gewichteter Mittelwert der Teilwerte, siehe Aufschlüsselung).")
    parts.append(f"Status: {STATUS_LABELS[det.status]}. {det.status_reason}.")
    parts += [f"{s.title}: {s.trigger_rule}." for s in det.scenarios]
    det.explanation = " ".join(parts)


def finalize(ctx: Context, det: Detection, conf_rule: str, inv_rule: str) -> Detection:
    apply_confidence(det)
    evaluate_status(ctx, det)
    build_scenarios(ctx, det, conf_rule, inv_rule)
    build_explanation(ctx, det)
    return det


def dedupe(dets: list[Detection]) -> list[Detection]:
    """Überlappen sich zwei Erkennungen derselben Familie um mindestens die Hälfte der kürzeren, bleibt die
    mit der höheren Konfidenz (bei Gleichstand die längere, dann die frühere)."""
    ranked = sorted(dets, key=lambda d: (-d.confidence, -(d.end_idx - d.start_idx), d.start_idx, d.pattern_type))
    kept: list[Detection] = []
    for d in ranked:
        clash = False
        for k in kept:
            if k.family != d.family:
                continue
            overlap = min(k.end_idx, d.end_idx) - max(k.start_idx, d.start_idx)
            shorter = max(1, min(k.end_idx - k.start_idx, d.end_idx - d.start_idx))
            if overlap / shorter >= 0.5:
                clash = True
                break
        if not clash:
            kept.append(d)
    return sorted(kept, key=lambda d: (d.start_idx, d.pattern_type))
