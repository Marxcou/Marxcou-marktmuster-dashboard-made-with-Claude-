"""Wendepunkte (Pivots) per ZigZag mit ATR-Schwelle. Alle Muster bauen auf diesen Pivots auf.

Ein Hoch gilt als Wendepunkt, sobald der Kurs von dort um mindestens max(atr_faktor × ATR, min_bewegung_pct)
gefallen ist (Tief entsprechend). `confirmed_idx` ist die Kerze, an der das feststand: bis dahin war der
Wendepunkt nicht bekannt (wichtig für den Backtest ohne Blick in die Zukunft)."""
from dataclasses import dataclass
from typing import Literal

from app.analysis.series import Bars, FloatArray


@dataclass(frozen=True)
class Pivot:
    idx: int
    kind: Literal["H", "L"]
    price: float
    confirmed_idx: int


def zigzag(bars: Bars, atr_values: FloatArray, atr_factor: float, min_move_pct: float) -> list[Pivot]:
    n = len(bars)
    if n < 2:
        return []
    high, low = bars.high, bars.low

    def threshold(i: int, price: float) -> float:
        return max(atr_factor * float(atr_values[i]), min_move_pct / 100.0 * price)

    pivots: list[Pivot] = []
    state = 0  # 0 = Richtung offen, 1 = steigend (Hoch-Kandidat), -1 = fallend (Tief-Kandidat)
    hi_i = lo_i = 0
    for i in range(1, n):
        if state == 0:
            if high[i] > high[hi_i]:
                hi_i = i
            if low[i] < low[lo_i]:
                lo_i = i
            if lo_i < i and high[i] - low[lo_i] >= threshold(lo_i, low[lo_i]) and lo_i < hi_i:
                pivots.append(Pivot(lo_i, "L", float(low[lo_i]), i))
                state, hi_i = 1, i
            elif hi_i < i and high[hi_i] - low[i] >= threshold(hi_i, high[hi_i]) and hi_i < lo_i:
                pivots.append(Pivot(hi_i, "H", float(high[hi_i]), i))
                state, lo_i = -1, i
        elif state == 1:
            if high[i] > high[hi_i]:
                hi_i = i
            elif high[hi_i] - low[i] >= threshold(hi_i, high[hi_i]):
                pivots.append(Pivot(hi_i, "H", float(high[hi_i]), i))
                state, lo_i = -1, i
        else:
            if low[i] < low[lo_i]:
                lo_i = i
            elif high[i] - low[lo_i] >= threshold(lo_i, low[lo_i]):
                pivots.append(Pivot(lo_i, "L", float(low[lo_i]), i))
                state, hi_i = 1, i
    return pivots
