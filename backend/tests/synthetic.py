"""Synthetische Kursreihen mit bekanntem Ergebnis für die Muster-Tests: stückweise lineare Verläufe durch
Stützpunkte (Kerze, Kurs). Hoch/Tief liegen 0,2 % über/unter Eröffnung bzw. Schluss. Keine Zufallszahlen."""
from datetime import UTC, datetime, timedelta

import numpy as np

from app.analysis.series import Bars

START = datetime(2024, 1, 1, tzinfo=UTC)


def path(anchors: list[tuple[int, float]], volume: list[float] | None = None, spread: float = 0.002) -> Bars:
    xs = [a[0] for a in anchors]
    ys = [a[1] for a in anchors]
    n = xs[-1] + 1
    close = np.interp(np.arange(n), xs, ys)
    open_ = np.concatenate(([close[0]], close[:-1]))
    high = np.maximum(open_, close) * (1 + spread)
    low = np.minimum(open_, close) * (1 - spread)
    ts = [START + timedelta(days=i) for i in range(n)]
    return Bars.from_lists(ts, open_.tolist(), high.tolist(), low.tolist(), close.tolist(), volume)


def flat_volume(n: int, value: float = 1_000_000) -> list[float]:
    return [value] * n
