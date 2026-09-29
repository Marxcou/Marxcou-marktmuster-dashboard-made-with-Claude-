"""Kerzenreihe als numpy-Arrays und ATR (Average True Range nach Wilder)."""
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True)
class Bars:
    ts: tuple[datetime, ...]
    open: FloatArray
    high: FloatArray
    low: FloatArray
    close: FloatArray
    volume: FloatArray  # NaN, wo die Quelle kein Volumen liefert

    def __len__(self) -> int:
        return len(self.ts)

    @classmethod
    def from_lists(
        cls, ts: Sequence[datetime], open_: Sequence[float], high: Sequence[float], low: Sequence[float],
        close: Sequence[float], volume: Sequence[float | None] | None = None,
    ) -> "Bars":
        n = len(ts)
        vol = [np.nan if v is None else float(v) for v in volume] if volume is not None else [np.nan] * n
        arrays = [np.asarray(a, dtype=np.float64) for a in (open_, high, low, close, vol)]
        if any(len(a) != n for a in arrays):
            raise ValueError("Alle Spalten brauchen dieselbe Länge")
        return cls(tuple(ts), *arrays)

    @property
    def has_volume(self) -> bool:
        """Volumen gilt als verfügbar, wenn mindestens 90 % der Kerzen einen positiven Wert haben."""
        if len(self) == 0:
            return False
        ok = np.isfinite(self.volume) & (self.volume > 0)
        return bool(ok.mean() >= 0.9)


def true_range(bars: Bars) -> FloatArray:
    prev_close = np.concatenate(([bars.close[0]], bars.close[:-1]))
    tr = np.maximum(bars.high - bars.low, np.maximum(np.abs(bars.high - prev_close), np.abs(bars.low - prev_close)))
    tr[0] = bars.high[0] - bars.low[0]
    return tr


def atr(bars: Bars, period: int) -> FloatArray:
    """Wilder-ATR. Vor der ersten vollen Periode: Mittel der bisherigen True Ranges (keine Lücke am Anfang)."""
    tr = true_range(bars)
    out = np.empty_like(tr)
    for i in range(len(tr)):
        if i < period:
            out[i] = tr[: i + 1].mean()
        else:
            out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out


def mean_volume(bars: Bars, start: int, end: int) -> float:
    """Mittleres Volumen der Kerzen start..end (inklusive), NaN ignoriert."""
    s, e = max(0, start), min(len(bars) - 1, end)
    window = bars.volume[s : e + 1]
    window = window[np.isfinite(window)]
    return float(window.mean()) if window.size else float("nan")
