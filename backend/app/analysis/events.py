"""Indikator-Ereignisse: Golden/Death Cross, RSI-Divergenz, Bollinger-Ausbruch, Volumenspitze.
Regelbasiert und deterministisch: gleiche Kerzen + gleiche Parameter = gleiche Ereignisse. Jedes Ereignis
trägt seine Kriterien mit den tatsächlichen Werten (Erklärpflicht) und die verwendeten Parameter.
Die Beschreibungen sind neutral und enthalten keine Handlungsaufforderung (Grundregel 1)."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np

from app.analysis import indicators as ind
from app.analysis.fmt import num, price, stamp

ALGO_VERSION = "indicator-events-1"
F64 = np.ndarray

PARAMS: dict[str, dict[str, Any]] = {
    "cross": {"fast": 50, "slow": 200},
    "rsi_divergence": {"rsi_period": 14, "pivot_window": 5, "min_bars_apart": 5, "max_bars_apart": 60,
                       "min_price_diff_pct": 0.1, "min_rsi_diff": 2.0, "rsi_midline": 50.0},
    "bollinger": {"period": 20, "factor": 2.0},
    "volume_spike": {"lookback": 20, "min_z": 3.0, "min_ratio": 2.0},
}


@dataclass
class Series:
    """Abgeschlossene Kerzen in aufsteigender Zeit. volume ist NaN, wenn die Quelle keines liefert."""
    ts: list[datetime]
    open: F64
    high: F64
    low: F64
    close: F64
    volume: F64
    timeframe: str
    currency: str

    def __len__(self) -> int:
        return len(self.ts)


@dataclass
class Event:
    type: str
    direction: str | None
    index: int  # Kerze der Markierung
    confirmed_index: int  # Kerze, ab der das Ereignis erkennbar war
    start_index: int
    title: str
    summary: str
    criteria: list[dict[str, Any]]
    values: dict[str, Any]
    params: dict[str, Any]
    ts: datetime = field(init=False)


def _crit(name: str, rule: str, required: str, actual: str, passed: bool = True) -> dict[str, Any]:
    return {"name": name, "rule": rule, "required": required, "actual": actual, "passed": passed}


def _f(x: float) -> float:
    return float(x)


def detect_crosses(s: Series) -> list[Event]:
    p = PARAMS["cross"]
    fast, slow = ind.sma(s.close, p["fast"]), ind.sma(s.close, p["slow"])
    out: list[Event] = []
    for i in range(1, len(s)):
        vals = (fast[i - 1], slow[i - 1], fast[i], slow[i])
        if any(np.isnan(v) for v in vals):
            continue
        f0, s0, f1, s1 = vals
        up = f0 <= s0 and f1 > s1
        down = f0 >= s0 and f1 < s1
        if not (up or down):
            continue
        fl, sl = f"SMA({p['fast']})", f"SMA({p['slow']})"
        cur = s.currency
        if up:
            typ, direction = "golden_cross", "up"
            title = f"Golden Cross ({fl} über {sl})"
            crit = [
                _crit("Vorkerze: schneller Durchschnitt nicht über dem langsamen", f"{fl} ≤ {sl}",
                      f"≤ {price(s0, cur)}", price(f0, cur)),
                _crit("Kerze: schneller Durchschnitt über dem langsamen", f"{fl} > {sl}",
                      f"> {price(s1, cur)}", price(f1, cur)),
            ]
            summary = (f"Am {stamp(s.ts[i], s.timeframe)} stieg der {fl} auf {price(f1, cur)} und lag damit über dem "
                       f"{sl} ({price(s1, cur)}); an der Vorkerze lag er noch bei {price(f0, cur)} "
                       f"(≤ {price(s0, cur)}).")
        else:
            typ, direction = "death_cross", "down"
            title = f"Death Cross ({fl} unter {sl})"
            crit = [
                _crit("Vorkerze: schneller Durchschnitt nicht unter dem langsamen", f"{fl} ≥ {sl}",
                      f"≥ {price(s0, cur)}", price(f0, cur)),
                _crit("Kerze: schneller Durchschnitt unter dem langsamen", f"{fl} < {sl}",
                      f"< {price(s1, cur)}", price(f1, cur)),
            ]
            summary = (f"Am {stamp(s.ts[i], s.timeframe)} fiel der {fl} auf {price(f1, cur)} und lag damit unter dem "
                       f"{sl} ({price(s1, cur)}); an der Vorkerze lag er noch bei {price(f0, cur)} "
                       f"(≥ {price(s0, cur)}).")
        out.append(Event(typ, direction, i, i, i - 1, title, summary, crit,
                         {"sma_fast": _f(f1), "sma_slow": _f(s1), "sma_fast_prev": _f(f0), "sma_slow_prev": _f(s0),
                          "close": _f(s.close[i])}, dict(p)))
    return out


def _pivots(x: F64, k: int, low: bool) -> list[int]:
    """Extrempunkte: Kerze i ist Tief/Hoch, wenn sie die k Kerzen links (nicht strikt) und rechts (strikt) übertrifft.
    Ein Pivot ist erst k Kerzen später bestätigt."""
    res = []
    for i in range(k, len(x) - k):
        left, right = x[i - k:i], x[i + 1:i + k + 1]
        if low and x[i] <= left.min() and x[i] < right.min():
            res.append(i)
        elif not low and x[i] >= left.max() and x[i] > right.max():
            res.append(i)
    return res


def detect_rsi_divergences(s: Series) -> list[Event]:
    p = PARAMS["rsi_divergence"]
    k = p["pivot_window"]
    rsi = ind.rsi(s.close, p["rsi_period"])
    out: list[Event] = []
    cur = s.currency
    rl = f"RSI({p['rsi_period']})"
    for low in (True, False):
        series = s.low if low else s.high
        piv = [i for i in _pivots(series, k, low) if not np.isnan(rsi[i])]
        for a, b in zip(piv, piv[1:], strict=False):
            apart = b - a
            p1, p2, r1, r2 = series[a], series[b], rsi[a], rsi[b]
            diff_pct = (p1 - p2) / p1 * 100 if low else (p2 - p1) / p1 * 100  # >0: Kurs weiter in Richtung
            rsi_diff = (r2 - r1) if low else (r1 - r2)
            zone_ok = r1 < p["rsi_midline"] if low else r1 > p["rsi_midline"]
            if not (p["min_bars_apart"] <= apart <= p["max_bars_apart"] and diff_pct >= p["min_price_diff_pct"]
                    and rsi_diff >= p["min_rsi_diff"] and zone_ok):
                continue
            what, ext = ("Tief", "tieferes") if low else ("Hoch", "höheres")
            rsi_ext = "höheres" if low else "tieferes"
            crit = [
                _crit(f"Abstand der Kurs-{what}s", "Kerzen zwischen den Extrempunkten",
                      f"{p['min_bars_apart']} bis {p['max_bars_apart']}", str(apart)),
                _crit(f"{ext.capitalize()} Kurs-{what}", f"{what} 2 {'<' if low else '>'} {what} 1, Mindestabstand "
                      f"{num(p['min_price_diff_pct'], 1)} %",
                      f"{'<' if low else '>'} {price(p1, cur)}", f"{price(p2, cur)} ({num(diff_pct)} % Abstand)"),
                _crit(f"{rsi_ext.capitalize()} RSI-{what}", f"{rl} 2 {'>' if low else '<'} {rl} 1, mindestens "
                      f"{num(p['min_rsi_diff'], 1)} Punkte Unterschied",
                      f"{'>' if low else '<'} {num(r1, 1)}", f"{num(r2, 1)} ({num(rsi_diff, 1)} Punkte)"),
                _crit(f"Lage von {rl} am ersten {what}", f"{rl} {'<' if low else '>'} {num(p['rsi_midline'], 0)}",
                      f"{'<' if low else '>'} {num(p['rsi_midline'], 0)}", num(r1, 1)),
            ]
            summary = (f"Der Kurs bildete am {stamp(s.ts[b], s.timeframe)} ein {ext} {what} ({price(p2, cur)} statt "
                       f"{price(p1, cur)} am {stamp(s.ts[a], s.timeframe)}), der {rl} dagegen ein {rsi_ext} {what} "
                       f"({num(r2, 1)} statt {num(r1, 1)}). Dieses Auseinanderlaufen ist eine beschreibende "
                       f"Beobachtung, keine Aussage über den weiteren Verlauf.")
            out.append(Event("rsi_divergence", "up" if low else "down", b, b + k, a,
                             f"RSI-Divergenz ({'Kurs tiefer, RSI höher' if low else 'Kurs höher, RSI tiefer'})",
                             summary, crit,
                             {"pivot1": {"ts": s.ts[a].isoformat(), "price": _f(p1), "rsi": _f(r1)},
                              "pivot2": {"ts": s.ts[b].isoformat(), "price": _f(p2), "rsi": _f(r2)},
                              "bars_apart": apart}, dict(p)))
    return sorted(out, key=lambda e: (e.index, e.direction or ""))


def detect_bollinger_breakouts(s: Series) -> list[Event]:
    p = PARAMS["bollinger"]
    mid, up, lo = ind.bollinger(s.close, p["period"], p["factor"])
    out: list[Event] = []
    cur = s.currency
    band = f"Bollinger-Band ({p['period']}, {num(p['factor'], 1)} σ)"
    for i in range(1, len(s)):
        if np.isnan(up[i]) or np.isnan(up[i - 1]):
            continue
        c1, c0 = s.close[i], s.close[i - 1]
        for direction, edge, edge0, above in (("up", up[i], up[i - 1], True), ("down", lo[i], lo[i - 1], False)):
            crossed = (c1 > edge and c0 <= edge0) if above else (c1 < edge and c0 >= edge0)
            if not crossed:
                continue
            side = "oberen" if above else "unteren"
            width = (up[i] - lo[i]) / mid[i] * 100
            pct_b = (c1 - lo[i]) / (up[i] - lo[i]) if up[i] != lo[i] else float("nan")
            crit = [
                _crit("Vorkerze innerhalb des Bandes", f"Schluss {'≤ oberes' if above else '≥ unteres'} Band",
                      f"{'≤' if above else '≥'} {price(edge0, cur)}", price(c0, cur)),
                _crit(f"Schluss außerhalb des {side} Bandes", f"Schluss {'>' if above else '<'} "
                      f"{'oberes' if above else 'unteres'} Band", f"{'>' if above else '<'} {price(edge, cur)}",
                      price(c1, cur)),
            ]
            summary = (f"Am {stamp(s.ts[i], s.timeframe)} schloss der Kurs bei {price(c1, cur)} "
                       f"{'über' if above else 'unter'} dem {side} {band} ({price(edge, cur)}); "
                       f"die Vorkerze lag mit {price(c0, cur)} noch innerhalb. "
                       f"Bandbreite {num(width)} % des Mittelbandes ({price(mid[i], cur)}).")
            out.append(Event("bb_breakout", direction, i, i, i - 1,
                             f"Schluss außerhalb des {side} Bollinger-Bandes", summary, crit,
                             {"close": _f(c1), "upper": _f(up[i]), "middle": _f(mid[i]), "lower": _f(lo[i]),
                              "close_prev": _f(c0), "bandwidth_pct": _f(width),
                              "percent_b": None if np.isnan(pct_b) else _f(pct_b)}, dict(p)))
    return out


def detect_volume_spikes(s: Series) -> list[Event]:
    p = PARAMS["volume_spike"]
    n = p["lookback"]
    out: list[Event] = []
    for i in range(n, len(s)):
        window = s.volume[i - n:i]
        v = s.volume[i]
        if np.isnan(v) or np.isnan(window).any():
            continue
        mean, std = window.mean(), window.std()
        if std == 0 or mean <= 0:
            continue
        z, ratio = (v - mean) / std, v / mean
        if z < p["min_z"] or ratio < p["min_ratio"]:
            continue
        crit = [
            _crit("Abweichung vom Mittel der Vorkerzen", f"z = (Volumen − Mittel) / Standardabweichung, {n} Vorkerzen",
                  f"≥ {num(p['min_z'], 1)}", num(z, 1)),
            _crit("Verhältnis zum Mittel", f"Volumen / Mittel der {n} Vorkerzen",
                  f"≥ {num(p['min_ratio'], 1)}", f"{num(ratio, 1)}×"),
        ]
        summary = (f"Am {stamp(s.ts[i], s.timeframe)} lag das Volumen bei {num(v, 0)} und damit beim "
                   f"{num(ratio, 1)}-fachen des Mittels der {n} Vorkerzen ({num(mean, 0)}); z-Wert {num(z, 1)}.")
        out.append(Event("volume_spike", None, i, i, i - n, "Ungewöhnlich hohes Handelsvolumen", summary, crit,
                         {"volume": _f(v), "mean": _f(mean), "std": _f(std), "z": _f(z), "ratio": _f(ratio)},
                         dict(p)))
    return out


def detect_all(s: Series) -> list[Event]:
    events = (detect_crosses(s) + detect_rsi_divergences(s) + detect_bollinger_breakouts(s)
              + detect_volume_spikes(s))
    for e in events:
        e.ts = s.ts[e.index]
    return sorted(events, key=lambda e: (e.index, e.type, e.direction or ""))
