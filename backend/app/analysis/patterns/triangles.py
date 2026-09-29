"""Dreiecke (aufsteigend, absteigend, symmetrisch) und Keile (steigend, fallend).

Kandidaten sind 4 bis 6 aufeinanderfolgende Wendepunkte. Durch die Hochs und durch die Tiefs wird je eine
Gerade nach der Methode der kleinsten Quadrate gelegt. Der Typ ergibt sich aus den Steigungen der beiden
Linien (in % des mittleren Schlusskurses je Kerze)."""
import numpy as np

from app.analysis import fmt
from app.analysis.patterns.common import (
    Context,
    Criterion,
    Detection,
    Direction,
    KeyPoint,
    Line,
    all_required_pass,
    crit_ge,
    crit_le,
    deadline,
    finalize,
    score_ge,
    score_le,
    volume_ratio_criterion,
)
from app.analysis.pivots import Pivot

WEIGHTS = {"form": 0.25, "verengung": 0.20, "anpassung": 0.20, "beruehrungen": 0.15, "innerhalb": 0.10,
           "volumen": 0.10}

TYPES: dict[str, tuple[str, Direction]] = {
    "dreieck_aufsteigend": ("Aufsteigendes Dreieck", "aufwärts"),
    "dreieck_absteigend": ("Absteigendes Dreieck", "abwärts"),
    "dreieck_symmetrisch": ("Symmetrisches Dreieck", "offen"),
    "keil_steigend": ("Steigender Keil", "abwärts"),
    "keil_fallend": ("Fallender Keil", "aufwärts"),
}


def _fit(points: list[Pivot]) -> tuple[float, float, float]:
    """Gerade durch die Punkte: (Steigung je Kerze, Achsenabschnitt, größte Abweichung in %)."""
    x = np.array([p.idx for p in points], dtype=np.float64)
    y = np.array([p.price for p in points], dtype=np.float64)
    slope, intercept = np.polyfit(x, y, 1)
    dev = float(np.max(np.abs(y - (slope * x + intercept)) / y * 100))
    return float(slope), float(intercept), dev


def classify(s_up: float, s_lo: float, flat: float, min_slope: float) -> str | None:
    if abs(s_up) <= flat and s_lo >= min_slope:
        return "dreieck_aufsteigend"
    if abs(s_lo) <= flat and s_up <= -min_slope:
        return "dreieck_absteigend"
    if s_up <= -min_slope and s_lo >= min_slope:
        return "dreieck_symmetrisch"
    if s_up >= min_slope and s_lo >= min_slope and s_lo > s_up:
        return "keil_steigend"
    if s_up <= -min_slope and s_lo <= -min_slope and s_up < s_lo:
        return "keil_fallend"
    return None


def find_triangles(ctx: Context) -> list[Detection]:
    p = ctx.params["dreieck_keil"]
    out: list[Detection] = []
    pv = ctx.pivots
    for m in range(int(p["min_pivots"]), int(p["max_pivots"]) + 1):
        for k in range(0, len(pv) - m + 1):
            det = _candidate(ctx, pv[k : k + m])
            if det is not None:
                out.append(det)
    return out


def _candidate(ctx: Context, seq: list[Pivot]) -> Detection | None:
    p = ctx.params["dreieck_keil"]
    highs = [q for q in seq if q.kind == "H"]
    lows = [q for q in seq if q.kind == "L"]
    if len(highs) < 2 or len(lows) < 2:
        return None
    start, end = seq[0].idx, seq[-1].idx
    width = end - start
    if not (p["min_breite_kerzen"] <= width <= p["max_breite_kerzen"]):
        return None
    close = ctx.bars.close
    ref = float(close[start : end + 1].mean())
    su, bu, dev_u = _fit(highs)
    sl, bl, dev_l = _fit(lows)
    s_up, s_lo = su / ref * 100, sl / ref * 100
    ptype = classify(s_up, s_lo, p["flach_steigung_pct"], p["min_steigung_pct"])
    if ptype is None:
        return None
    upper = Line("obere_linie", "Obere Begrenzung", start, su * start + bu, end, su * end + bu)
    lower = Line("untere_linie", "Untere Begrenzung", start, sl * start + bl, end, sl * end + bl)
    w0, w1 = upper.at(start) - lower.at(start), upper.at(end) - lower.at(end)
    if w0 <= 0 or w1 <= 0:
        return None
    name, direction = TYPES[ptype]
    crit: list[Criterion] = []

    flat, mn = p["flach_steigung_pct"], p["min_steigung_pct"]
    form_text = f"Steigung obere Linie {fmt.num(s_up, 3)} % je Kerze, untere Linie {fmt.num(s_lo, 3)} % je Kerze"
    if ptype == "dreieck_aufsteigend":
        rule = f"obere Linie waagerecht (|Steigung| ≤ {fmt.num(flat)} %), untere steigt (≥ {fmt.num(mn)} %)"
        sub = (score_le(abs(s_up), 0, flat) + score_ge(s_lo, 3 * mn, mn)) / 2
    elif ptype == "dreieck_absteigend":
        rule = f"untere Linie waagerecht (|Steigung| ≤ {fmt.num(flat)} %), obere fällt (≤ −{fmt.num(mn)} %)"
        sub = (score_le(abs(s_lo), 0, flat) + score_ge(-s_up, 3 * mn, mn)) / 2
    elif ptype == "dreieck_symmetrisch":
        rule = f"obere Linie fällt und untere steigt, je mindestens {fmt.num(mn)} % je Kerze"
        sub = (score_ge(-s_up, 3 * mn, mn) + score_ge(s_lo, 3 * mn, mn)) / 2
    elif ptype == "keil_steigend":
        rule = f"beide Linien steigen (≥ {fmt.num(mn)} % je Kerze), die untere steiler"
        sub = (score_ge(min(s_up, s_lo), 3 * mn, mn) + 1.0) / 2
    else:
        rule = f"beide Linien fallen (≤ −{fmt.num(mn)} % je Kerze), die obere steiler"
        sub = (score_ge(-max(s_up, s_lo), 3 * mn, mn) + 1.0) / 2
    crit.append(Criterion("form", "Verlauf der Linien", rule, None, round(s_lo - s_up, 4), "% je Kerze",
                          form_text, True, True, round(sub, 4), WEIGHTS["form"]))

    narrowing = (1 - w1 / w0) * 100
    crit.append(crit_ge(
        "verengung", "Verengung der Spanne",
        f"Spanne verengt sich um mindestens {fmt.pct(p['min_verengung_pct'], 0)}", narrowing, p["min_verengung_pct"],
        p["ideal_verengung_pct"], "%",
        f"Spanne am {ctx.date(start)}: {fmt.price(w0)}, am {ctx.date(end)}: {fmt.price(w1)}, "
        f"Verengung {fmt.pct(narrowing, 1)}", WEIGHTS["verengung"]))

    dev = max(dev_u, dev_l)
    crit.append(crit_le(
        "anpassung", "Lage der Wendepunkte an den Linien",
        f"jeder Wendepunkt höchstens {fmt.pct(p['max_anpassung_pct'], 1)} von seiner Linie entfernt",
        dev, p["max_anpassung_pct"], 0.0, "%",
        f"größte Abweichung {fmt.pct(dev)} ({len(highs)} Hochs, {len(lows)} Tiefs)", WEIGHTS["anpassung"]))

    touches = min(len(highs), len(lows))
    crit.append(crit_ge(
        "beruehrungen", "Berührungen je Linie", "mindestens 2 Wendepunkte an jeder Linie", float(touches), 2.0, 3.0,
        "Anzahl", f"{len(highs)} Berührungen oben, {len(lows)} unten", WEIGHTS["beruehrungen"]))

    tol = p["toleranz_atr"] * ctx.atr[start : end + 1]
    idx = np.arange(start, end + 1)
    up_v = su * idx + bu
    lo_v = sl * idx + bl
    c = close[start : end + 1]
    inside = float(np.mean((c <= up_v + tol) & (c >= lo_v - tol)) * 100)
    crit.append(crit_ge(
        "innerhalb", "Schlusskurse zwischen den Linien",
        f"mindestens {fmt.pct(p['min_anteil_innerhalb_pct'], 0)} der Schlusskurse zwischen den Linien "
        f"(Toleranz {fmt.num(p['toleranz_atr'], 1)} ATR)", inside, p["min_anteil_innerhalb_pct"], 100.0, "%",
        f"{fmt.pct(inside, 0)} der {end - start + 1} Schlusskurse innerhalb", WEIGHTS["innerhalb"]))

    half = start + width // 2
    vol = volume_ratio_criterion(
        ctx, "volumen", "Volumenverlauf", "Volumen in der zweiten Hälfte niedriger als in der ersten "
        "(Qualitätskriterium)", (half + 1, end), (start, half), "zweite Hälfte", "erste Hälfte", WEIGHTS["volumen"])
    if vol is not None:
        crit.append(vol)

    if not all_required_pass(crit):
        return None

    apex: int | None = None
    if su != sl:
        x = (bl - bu) / (su - sl)
        if x > end:
            apex = int(np.ceil(x))
    if direction == "abwärts":
        confirmation, invalidation = lower, upper
        conf_rule, inv_rule = "der unteren Begrenzung", "der oberen Begrenzung"
    else:
        confirmation, invalidation = upper, lower
        conf_rule, inv_rule = "der oberen Begrenzung", "der unteren Begrenzung"
    kps = [KeyPoint(f"beruehrung_oben_{i + 1}", f"Berührung oben {i + 1}", q.idx, q.price) for i, q in enumerate(highs)]
    kps += [KeyPoint(f"beruehrung_unten_{i + 1}", f"Berührung unten {i + 1}", q.idx, q.price)
            for i, q in enumerate(lows)]
    det = Detection(
        pattern_type=ptype, name=name, direction=direction, start_idx=start, end_idx=end,
        formed_idx=max(q.confirmed_idx for q in seq), key_points=sorted(kps, key=lambda k: k.idx),
        lines=[upper, lower], criteria=crit, confirmation=confirmation, invalidation=invalidation,
        deadline_idx=deadline(ctx, start, end), apex_idx=apex, family="dreieck_keil",
    )
    return finalize(ctx, det, conf_rule, inv_rule)
