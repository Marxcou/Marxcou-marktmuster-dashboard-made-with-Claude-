"""Flaggen und Wimpel: eine steile Bewegung (Fahnenstange) gefolgt von einer kurzen Konsolidierung.

Fahnenstangen-Ende i: höchstes Hoch (bzw. tiefstes Tief) der letzten `max_stange_kerzen` Kerzen, das in der
Konsolidierung nicht überschritten wird. Beginn: tiefstes Tief (höchstes Hoch) davor. Durch die Hochs und
die Tiefs der Konsolidierung wird je eine Regressionsgerade gelegt. Gewählt wird die längste Konsolidierung,
die alle Pflichtkriterien erfüllt und deren letzter Schlusskurs im Kanal liegt."""
import numpy as np

from app.analysis import fmt
from app.analysis.patterns.common import (
    Context,
    Criterion,
    Detection,
    KeyPoint,
    Line,
    all_required_pass,
    crit_ge,
    crit_le,
    finalize,
    volume_ratio_criterion,
)

WEIGHTS = {"stange": 0.25, "ruecksetzer": 0.15, "neigung": 0.15, "form": 0.15, "innerhalb": 0.10, "dauer": 0.10,
           "volumen": 0.10}


def find_flags(ctx: Context) -> list[Detection]:
    out: list[Detection] = []
    for up in (True, False):
        for i in range(len(ctx.bars)):
            det = _best_for_pole_end(ctx, i, up)
            if det is not None:
                out.append(det)
    return out


def _best_for_pole_end(ctx: Context, i: int, up: bool) -> Detection | None:
    p = ctx.params["flagge"]
    hi, lo = ctx.bars.high, ctx.bars.low
    max_pole, min_pole = int(p["max_stange_kerzen"]), int(p["min_stange_kerzen"])
    if i < min_pole:
        return None
    lookback = slice(max(0, i - max_pole), i + 1)
    if up and hi[i] < hi[lookback].max():
        return None
    if not up and lo[i] > lo[lookback].min():
        return None
    seg = slice(max(0, i - max_pole), i - min_pole + 1)
    if seg.stop <= seg.start:
        return None
    if up:
        j = seg.stop - 1 - int(np.argmin(lo[seg][::-1]))  # bei Gleichstand der späteste Punkt
        pole_start, pole_end = float(lo[j]), float(hi[i])
        pole_pct = (pole_end - pole_start) / pole_start * 100
    else:
        j = seg.stop - 1 - int(np.argmax(hi[seg][::-1]))
        pole_start, pole_end = float(hi[j]), float(lo[i])
        pole_pct = (pole_start - pole_end) / pole_start * 100
    if pole_pct < p["min_stange_pct"]:
        return None
    n = len(ctx.bars)
    for length in range(int(p["max_flagge_kerzen"]), int(p["min_flagge_kerzen"]) - 1, -1):
        end = i + length
        if end >= n:
            continue
        det = _candidate(ctx, j, i, end, up, pole_start, pole_end, pole_pct)
        if det is not None:
            return det
    return None


def _candidate(ctx: Context, j: int, i: int, end: int, up: bool, pole_start: float, pole_end: float,
               pole_pct: float) -> Detection | None:
    p = ctx.params["flagge"]
    hi, lo, close = ctx.bars.high, ctx.bars.low, ctx.bars.close
    w = slice(i + 1, end + 1)
    # Die Konsolidierung darf das Ende der Fahnenstange nicht überschreiten
    if (up and hi[w].max() > pole_end) or (not up and lo[w].min() < pole_end):
        return None
    x = np.arange(i + 1, end + 1, dtype=np.float64)
    su, bu = (float(v) for v in np.polyfit(x, hi[w], 1))
    sl, bl = (float(v) for v in np.polyfit(x, lo[w], 1))
    ref = float(close[w].mean())
    s_up, s_lo = su / ref * 100, sl / ref * 100
    upper = Line("obere_linie", "Obere Kanal-Linie", i + 1, su * (i + 1) + bu, end, su * end + bu)
    lower = Line("untere_linie", "Untere Kanal-Linie", i + 1, sl * (i + 1) + bl, end, sl * end + bl)
    if upper.at(end) <= lower.at(end):
        return None

    wm = p["wimpel_min_steigung_pct"]
    pennant = s_up <= -wm and s_lo >= wm
    mid = (s_up + s_lo) / 2
    against = -mid if up else mid  # > 0: Konsolidierung läuft gegen die Richtung der Fahnenstange
    parallel = abs(s_up - s_lo)
    if not pennant:
        if parallel > p["max_parallel_abweichung_pct"] or against < -p["max_gegen_steigung_pct"]:
            return None

    crit: list[Criterion] = []
    word = "Anstieg" if up else "Rückgang"
    crit.append(crit_ge(
        "stange", "Fahnenstange", f"{word} um mindestens {fmt.pct(p['min_stange_pct'], 0)} in "
        f"{int(p['min_stange_kerzen'])} bis {int(p['max_stange_kerzen'])} Kerzen", pole_pct, p["min_stange_pct"],
        p["ideal_stange_pct"], "%",
        f"{word} von {fmt.price(pole_start)} am {ctx.date(j)} auf {fmt.price(pole_end)} am {ctx.date(i)} "
        f"({fmt.pct(pole_pct, 1)} in {i - j} Kerzen)", WEIGHTS["stange"]))

    pole_h = abs(pole_end - pole_start)
    extreme = float(lo[w].min()) if up else float(hi[w].max())
    retrace = abs(pole_end - extreme) / pole_h * 100
    crit.append(crit_le(
        "ruecksetzer", "Rücksetzer in der Konsolidierung",
        f"höchstens {fmt.pct(p['max_ruecksetzer_pct'], 0)} der Fahnenstange", retrace, p["max_ruecksetzer_pct"],
        p["ideal_ruecksetzer_pct"], "%",
        f"{'Tiefster' if up else 'Höchster'} Kurs der Konsolidierung {fmt.price(extreme)}, "
        f"{fmt.pct(retrace, 1)} der Fahnenstange", WEIGHTS["ruecksetzer"]))

    pole_slope = pole_pct / (i - j)
    tilt = abs(mid) / pole_slope * 100
    crit.append(crit_le(
        "neigung", "Neigung der Konsolidierung",
        f"Kanal-Mitte höchstens {fmt.pct(p['max_neigung_anteil_pct'], 0)} so steil wie die Fahnenstange",
        tilt, p["max_neigung_anteil_pct"], p["max_neigung_anteil_pct"] / 4, "%",
        f"Kanal-Mitte {fmt.num(mid, 3)} % je Kerze, Fahnenstange {fmt.num(pole_slope, 3)} % je Kerze "
        f"({fmt.pct(tilt, 0)})", WEIGHTS["neigung"]))

    slopes = f"Steigung oben {fmt.num(s_up, 3)} %, unten {fmt.num(s_lo, 3)} % je Kerze"
    if pennant:
        crit.append(crit_ge(
            "form", "Zusammenlaufende Linien (Wimpel)",
            f"obere Linie fällt und untere steigt, je mindestens {fmt.num(wm)} % je Kerze",
            min(-s_up, s_lo), wm, 3 * wm, "% je Kerze", slopes, WEIGHTS["form"]))
    else:
        crit.append(crit_le(
            "form", "Parallele Linien (Flagge)",
            f"Steigungen unterscheiden sich höchstens um {fmt.num(p['max_parallel_abweichung_pct'])} % je Kerze, "
            "Kanal läuft waagerecht oder gegen die Fahnenstange", parallel, p["max_parallel_abweichung_pct"], 0.0,
            "% je Kerze", slopes + f", Unterschied {fmt.num(parallel, 3)}", WEIGHTS["form"]))

    tol = p["toleranz_atr"] * ctx.atr[w]
    c = close[w]
    inside_mask = (c <= su * x + bu + tol) & (c >= sl * x + bl - tol)
    if not bool(inside_mask[-1]):
        return None
    inside = float(inside_mask.mean() * 100)
    crit.append(crit_ge(
        "innerhalb", "Schlusskurse im Kanal",
        f"mindestens {fmt.pct(p['min_anteil_innerhalb_pct'], 0)} der Schlusskurse im Kanal "
        f"(Toleranz {fmt.num(p['toleranz_atr'], 2)} ATR)", inside, p["min_anteil_innerhalb_pct"], 100.0, "%",
        f"{fmt.pct(inside, 0)} der {end - i} Schlusskurse im Kanal", WEIGHTS["innerhalb"]))

    length = end - i
    crit.append(crit_le(
        "dauer", "Dauer der Konsolidierung",
        f"{int(p['min_flagge_kerzen'])} bis {int(p['max_flagge_kerzen'])} Kerzen", float(length),
        p["max_flagge_kerzen"], p["min_flagge_kerzen"] * 2, "Kerzen",
        f"{length} Kerzen von {ctx.date(i + 1)} bis {ctx.date(end)}", WEIGHTS["dauer"]))

    vol = volume_ratio_criterion(
        ctx, "volumen", "Volumen in der Konsolidierung",
        "Volumen in der Konsolidierung niedriger als in der Fahnenstange (Qualitätskriterium)",
        (i + 1, end), (j, i), "in der Konsolidierung", "in der Fahnenstange", WEIGHTS["volumen"])
    if vol is not None:
        crit.append(vol)

    if not all_required_pass(crit):
        return None

    kind = "wimpel" if pennant else "flagge"
    ptype = f"{kind}_{'aufwaerts' if up else 'abwaerts'}"
    name = f"{'Wimpel' if pennant else 'Flagge'} nach {'Anstieg' if up else 'Rückgang'}"
    inv = Line.horizontal("ungueltigkeit", "Ungültigkeitsniveau", i + 1, end, extreme)
    det = Detection(
        pattern_type=ptype, name=name, direction="aufwärts" if up else "abwärts", start_idx=j, end_idx=end,
        formed_idx=end,
        key_points=[
            KeyPoint("fahnenstange_start", "Beginn Fahnenstange", j, pole_start),
            KeyPoint("fahnenstange_ende", "Ende Fahnenstange", i, pole_end),
        ],
        lines=[upper, lower], criteria=crit,
        confirmation=upper if up else lower, invalidation=inv,
        deadline_idx=end + int(p["ausbruch_frist_kerzen"]), family=f"flagge_{'auf' if up else 'ab'}",
    )
    return finalize(ctx, det, f"der {'oberen' if up else 'unteren'} Kanal-Linie",
                    f"dem {'tiefsten' if up else 'höchsten'} Kurs der Konsolidierung")
