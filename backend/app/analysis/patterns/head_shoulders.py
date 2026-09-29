"""Kopf-Schulter-Formation (und invers) aus fünf aufeinanderfolgenden Wendepunkten:
Schulter, Nacken 1, Kopf, Nacken 2, Schulter. Die Nackenlinie verbindet die beiden Nackenpunkte."""
import math

from app.analysis import fmt
from app.analysis.patterns.common import (
    Context,
    Criterion,
    Detection,
    KeyPoint,
    Line,
    all_required_pass,
    around,
    crit_ge,
    crit_le,
    deadline,
    finalize,
    pct_diff,
    volume_ratio_criterion,
)

WEIGHTS = {"kopf": 0.25, "schultern": 0.25, "nacken": 0.15, "zeit": 0.15, "vortrend": 0.10, "volumen": 0.10}


def find_head_shoulders(ctx: Context) -> list[Detection]:
    out: list[Detection] = []
    pv = ctx.pivots
    for k in range(1, len(pv) - 4):
        seq = pv[k : k + 5]
        # normal: H L H L H (Kopf oben); invers: L H L H L
        inverse = seq[0].kind == "L"
        det = _candidate(ctx, pv[k - 1].price, [(s.idx, s.price) for s in seq], inverse, seq[-1].confirmed_idx)
        if det is not None:
            out.append(det)
    return out


def _candidate(ctx: Context, prev_price: float, pts: list[tuple[int, float]], inverse: bool,
               formed_idx: int) -> Detection | None:
    p = ctx.params["kopf_schulter"]
    (ils, pls), (in1, pn1), (ih, ph), (in2, pn2), (irs, prs) = pts
    width = irs - ils
    if not (p["min_breite_kerzen"] <= width <= p["max_breite_kerzen"]):
        return None
    sgn = -1.0 if inverse else 1.0  # invers: Werte spiegeln, damit dieselben Regeln gelten
    crit: list[Criterion] = []

    outer_shoulder = min(pls, prs) if inverse else max(pls, prs)
    overhang = sgn * (ph - outer_shoulder) / abs(outer_shoulder) * 100
    over = "unter" if inverse else "über"
    crit.append(crit_ge(
        "kopf_ueberhang", "Kopf gegenüber den Schultern",
        f"Kopf liegt mindestens {fmt.pct(p['min_kopf_ueberhang_pct'], 1)} {over} der "
        f"{'tieferen' if inverse else 'höheren'} Schulter",
        overhang, p["min_kopf_ueberhang_pct"], p["ideal_kopf_ueberhang_pct"], "%",
        f"Kopf: {fmt.price(ph)} am {ctx.date(ih)}, {fmt.pct(overhang)} {over} der Schulter bei "
        f"{fmt.price(outer_shoulder)}", WEIGHTS["kopf"]))

    sdev = pct_diff(pls, prs)
    crit.append(crit_le(
        "schulter_abweichung", "Symmetrie der Schultern",
        f"Schultern weichen höchstens {fmt.pct(p['max_schulter_abweichung_pct'], 1)} voneinander ab",
        sdev, p["max_schulter_abweichung_pct"], 0.0, "%",
        f"Linke Schulter: {fmt.price(pls)} am {ctx.date(ils)}, rechte Schulter: {fmt.price(prs)} am "
        f"{ctx.date(irs)}, Abweichung {fmt.pct(sdev)}", WEIGHTS["schultern"]))

    ndev = pct_diff(pn1, pn2)
    crit.append(crit_le(
        "nacken_neigung", "Neigung der Nackenlinie",
        f"Nackenpunkte weichen höchstens {fmt.pct(p['max_nacken_neigung_pct'], 1)} voneinander ab",
        ndev, p["max_nacken_neigung_pct"], 0.0, "%",
        f"Nacken 1: {fmt.price(pn1)} am {ctx.date(in1)}, Nacken 2: {fmt.price(pn2)} am {ctx.date(in2)}, "
        f"Unterschied {fmt.pct(ndev)}", WEIGHTS["nacken"]))

    left, right = ih - ils, irs - ih
    ratio = left / right if right else math.inf
    lo, hi = p["min_zeit_verhaeltnis"], p["max_zeit_verhaeltnis"]
    ok = lo <= ratio <= hi
    sub = max(0.0, 1 - abs(math.log(ratio)) / math.log(hi)) if ok and ratio > 0 else 0.0
    crit.append(Criterion(
        "zeit_symmetrie", "Zeitliche Symmetrie",
        f"Dauer linke Schulter bis Kopf / Kopf bis rechte Schulter zwischen {fmt.num(lo, 1)} und {fmt.num(hi, 1)}",
        hi, round(ratio, 4) if math.isfinite(ratio) else None, "Faktor",
        f"{left} Kerzen links, {right} Kerzen rechts, Verhältnis {fmt.num(ratio) if math.isfinite(ratio) else '–'}",
        True, ok, round(sub, 4), WEIGHTS["zeit"]))

    prior = sgn * (pls - prev_price) / prev_price * 100
    crit.append(crit_ge(
        "vortrend", "Vorheriger Rückgang" if inverse else "Vorheriger Anstieg",
        f"Bewegung vom vorherigen Wendepunkt zur linken Schulter mindestens {fmt.pct(p['min_vortrend_pct'], 1)}",
        prior, p["min_vortrend_pct"], p["ideal_vortrend_pct"], "%",
        f"{'Rückgang' if inverse else 'Anstieg'} von {fmt.price(prev_price)} auf {fmt.price(pls)} ({fmt.pct(prior)})",
        WEIGHTS["vortrend"]))

    vol = volume_ratio_criterion(
        ctx, "volumen", "Volumen an der rechten Schulter",
        "Volumen um die rechte Schulter niedriger als um den Kopf (Qualitätskriterium)",
        around(ctx, irs), around(ctx, ih), "um die rechte Schulter", "um den Kopf", WEIGHTS["volumen"])
    if vol is not None:
        crit.append(vol)

    if not all_required_pass(crit):
        return None
    # Die Nackenlinie muss zwischen Kopf und Schultern liegen
    neck = Line("nackenlinie", "Nackenlinie", in1, pn1, in2, pn2)
    if (max(pls, prs) >= min(pn1, pn2)) if inverse else (min(pls, prs) <= max(pn1, pn2)):
        return None

    buf = ctx.params["status"]["invalidierung_puffer_pct"] / 100
    inv_price = prs * (1 - buf) if inverse else prs * (1 + buf)
    det = Detection(
        pattern_type="kopf_schulter_invers" if inverse else "kopf_schulter",
        name="Inverse Kopf-Schulter-Formation" if inverse else "Kopf-Schulter-Formation",
        direction="aufwärts" if inverse else "abwärts",
        start_idx=ils, end_idx=irs, formed_idx=formed_idx,
        key_points=[
            KeyPoint("linke_schulter", "Linke Schulter", ils, pls),
            KeyPoint("nacken_1", "Nacken 1", in1, pn1),
            KeyPoint("kopf", "Kopf", ih, ph),
            KeyPoint("nacken_2", "Nacken 2", in2, pn2),
            KeyPoint("rechte_schulter", "Rechte Schulter", irs, prs),
        ],
        lines=[neck],
        criteria=crit,
        confirmation=neck,
        invalidation=Line.horizontal("ungueltigkeit", "Ungültigkeitsniveau", ils, irs, inv_price),
        deadline_idx=deadline(ctx, ils, irs),
        family="kopf_schulter_invers" if inverse else "kopf_schulter",
    )
    sign = "minus" if inverse else "plus"
    return finalize(ctx, det, "der Nackenlinie",
                    f"dem Ungültigkeitsniveau (rechte Schulter {sign} {fmt.pct(buf * 100, 1)})")
