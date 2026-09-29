"""Unterstützungs- und Widerstandszonen: Häufungen von Wendepunkten auf ähnlichem Kursniveau.

Die Wendepunkte der letzten `rueckblick_kerzen` werden nach Preis sortiert und gierig gruppiert: ein Punkt
gehört zur Gruppe, solange er höchstens eine Zonenbreite über dem niedrigsten Punkt der Gruppe liegt.
Zonenbreite = max(toleranz_atr × mittlere ATR, min_toleranz_pct × letzter Schlusskurs)."""
from dataclasses import dataclass, field

import numpy as np

from app.analysis import fmt
from app.analysis.patterns.common import (
    CONFIDENCE_METHOD,
    Context,
    Criterion,
    crit_ge,
    crit_le,
)
from app.analysis.pivots import Pivot

WEIGHTS = {"beruehrungen": 0.5, "aktualitaet": 0.3, "zeitspanne": 0.2}
KIND_LABELS = {"unterstuetzung": "Unterstützungszone", "widerstand": "Widerstandszone",
               "im_bereich": "Kurs innerhalb der Zone"}


@dataclass
class Zone:
    kind: str
    lower: float
    upper: float
    touches: list[Pivot]
    criteria: list[Criterion]
    confidence: float = 0.0
    breakdown: list[dict[str, float | str]] = field(default_factory=list)
    explanation: str = ""

    @property
    def center(self) -> float:
        return (self.lower + self.upper) / 2

    @property
    def kind_label(self) -> str:
        return KIND_LABELS[self.kind]


def find_zones(ctx: Context) -> list[Zone]:
    p = ctx.params["zonen"]
    n = len(ctx.bars)
    if n == 0:
        return []
    first = max(0, n - int(p["rueckblick_kerzen"]))
    pts = sorted((q for q in ctx.pivots if q.idx >= first), key=lambda q: (q.price, q.idx))
    last_close = float(ctx.bars.close[-1])
    width = max(p["toleranz_atr"] * float(np.mean(ctx.atr[first:])), p["min_toleranz_pct"] / 100 * last_close)
    groups: list[list[Pivot]] = []
    for q in pts:
        if groups and q.price - groups[-1][0].price <= width:
            groups[-1].append(q)
        else:
            groups.append([q])
    zones: list[Zone] = []
    for g in groups:
        z = _zone(ctx, g, last_close)
        if z is not None:
            zones.append(z)
    zones = sorted(zones, key=lambda z: (-z.confidence, z.lower))[: int(p["max_zonen"])]
    return sorted(zones, key=lambda z: z.lower)


def _zone(ctx: Context, g: list[Pivot], last_close: float) -> Zone | None:
    p = ctx.params["zonen"]
    n = len(ctx.bars)
    by_time = sorted(g, key=lambda q: q.idx)
    lower, upper = min(q.price for q in g), max(q.price for q in g)
    span = by_time[-1].idx - by_time[0].idx
    age = n - 1 - by_time[-1].idx
    crit = [
        crit_ge("beruehrungen", "Anzahl Wendepunkte in der Zone",
                f"mindestens {int(p['min_beruehrungen'])} Wendepunkte", float(len(g)), p["min_beruehrungen"],
                p["ideal_beruehrungen"], "Anzahl",
                f"{len(g)} Wendepunkte ({sum(q.kind == 'H' for q in g)} Hochs, {sum(q.kind == 'L' for q in g)} Tiefs) "
                f"zwischen {fmt.price(lower)} und {fmt.price(upper)}", WEIGHTS["beruehrungen"]),
        crit_ge("zeitspanne", "Zeitspanne der Berührungen",
                f"mindestens {int(p['min_zeitspanne_kerzen'])} Kerzen zwischen erster und letzter Berührung",
                float(span), p["min_zeitspanne_kerzen"], p["ideal_zeitspanne_kerzen"], "Kerzen",
                f"erste Berührung {ctx.date(by_time[0].idx)}, letzte {ctx.date(by_time[-1].idx)} ({span} Kerzen)",
                WEIGHTS["zeitspanne"]),
        crit_le("aktualitaet", "Aktualität", f"letzte Berührung höchstens {int(p['max_aktualitaet_kerzen'])} Kerzen "
                "her (Qualitätskriterium)", float(age), p["max_aktualitaet_kerzen"], p["ideal_aktualitaet_kerzen"],
                "Kerzen", f"letzte Berührung vor {age} Kerzen", WEIGHTS["aktualitaet"], required=False),
    ]
    # Mindestanzahl als Teilwert: bei genau der Mindestzahl nicht 0, sondern ab (Mindestzahl − 1) linear
    crit[0].sub_score = round(min(1.0, max(0.0, (len(g) - p["min_beruehrungen"] + 1)
                                           / (p["ideal_beruehrungen"] - p["min_beruehrungen"] + 1))), 4)
    if not all(c.passed for c in crit if c.required):
        return None
    if last_close < lower:
        kind = "widerstand"
    elif last_close > upper:
        kind = "unterstuetzung"
    else:
        kind = "im_bereich"
    z = Zone(kind, round(lower, 4), round(upper, 4), by_time, crit)
    total = sum(c.weight for c in crit)
    for c in crit:
        w = c.weight / total
        z.breakdown.append({"key": c.key, "name": c.name, "weight": round(w, 4), "sub_score": c.sub_score,
                            "contribution": round(w * c.sub_score, 4)})
    z.confidence = round(sum(float(b["contribution"]) for b in z.breakdown), 4)
    z.explanation = (f"{z.kind_label} zwischen {fmt.price(lower)} und {fmt.price(upper)}: "
                     + ". ".join(c.actual_text for c in crit)
                     + f". Letzter Schlusskurs {fmt.price(last_close)}. Konfidenz {fmt.pct(z.confidence * 100, 0)}.")
    return z


ZONE_CONFIDENCE_METHOD = CONFIDENCE_METHOD
