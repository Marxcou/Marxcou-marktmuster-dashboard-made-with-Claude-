"""Erzeugt die festen Kerzen-Fixtures (CSV) der Muster-Regressionstests. Nur bei bewusst geänderten Fixtures ausführen:

    cd backend && python -m tests.regression.make_fixtures

Die CSV-Dateien sind die Wahrheit der Tests; dieses Skript dokumentiert nur, wie sie entstanden (synthetische
Stützpunktverläufe, keine echten Marktdaten; Zufallsreihe mit festem Startwert)."""
import csv
from pathlib import Path

import numpy as np

from tests.synthetic import flat_volume, path

OUT = Path(__file__).parent / "fixtures"


def mirror(anchors: list[tuple[int, float]]) -> list[tuple[int, float]]:
    return [(i, 200 - p) for i, p in anchors]


WIMPEL_AUF = [(0, 100), (40, 100), (48, 120), (50, 116), (52, 119.5), (54, 116.8), (56, 118.8), (58, 117.4),
              (60, 118.3), (62, 117.8), (70, 126), (80, 128)]

ANCHORS: dict[str, list[tuple[int, float]]] = {
    "doppelboden": [(0, 120), (30, 100), (45, 110), (60, 100.3), (80, 118), (100, 125)],
    "doppelhoch": [(0, 80), (30, 100), (45, 90), (60, 99.7), (80, 82), (100, 78)],
    "kopf_schulter": [(0, 80), (20, 100), (30, 92), (45, 108), (60, 92.5), (75, 100.5), (95, 82), (110, 80)],
    "kopf_schulter_invers": [(0, 120), (20, 100), (30, 108), (45, 92), (60, 107.5), (75, 99.5), (95, 118),
                             (110, 120)],
    "dreieck_aufsteigend": [(0, 120), (25, 90), (35, 110), (45, 97), (55, 110), (65, 103), (75, 110), (80, 107),
                            (90, 118), (100, 120)],
    "dreieck_absteigend": [(0, 80), (25, 110), (35, 90), (45, 103), (55, 90), (65, 97), (75, 90), (80, 93),
                           (90, 82), (100, 80)],
    "dreieck_symmetrisch": [(0, 70), (25, 110), (35, 90), (45, 106), (55, 94), (65, 102), (75, 97), (80, 100),
                            (90, 108), (100, 110)],
    "keil_steigend": [(0, 120), (25, 90), (35, 100), (45, 95), (55, 105), (65, 101), (75, 109), (80, 106),
                      (90, 95), (100, 92)],
    "keil_fallend": [(0, 80), (25, 110), (35, 100), (45, 105), (55, 95), (65, 99), (75, 91), (80, 94), (90, 105),
                     (100, 108)],
    "flagge_aufwaerts": [(0, 100), (40, 100), (48, 120), (60, 116), (62, 117), (70, 126), (80, 128)],
    "flagge_abwaerts": [(0, 120), (40, 120), (48, 100), (60, 104), (62, 103), (70, 94), (80, 92)],
    "wimpel_aufwaerts": WIMPEL_AUF,
    "wimpel_abwaerts": mirror(WIMPEL_AUF),
    # Doppelboden, der vor der Bestätigung scheitert (Kurs fällt unter den Extrempunkt)
    "doppelboden_gescheitert": [(0, 120), (30, 100), (45, 110), (60, 100.3), (70, 104), (85, 90), (100, 88)],
    # Doppelboden noch in Bildung (Serie endet vor dem Überschreiten der Nackenlinie)
    "doppelboden_in_bildung": [(0, 120), (30, 100), (45, 110), (60, 100.3), (70, 106)],
    # Negativfälle: nichts darf erkannt werden
    "seitwaerts_flach": [(0, 100), (120, 100)],
    "trend_steigend": [(0, 50), (120, 150)],
}


def write(name: str, bars) -> None:  # type: ignore[no-untyped-def]
    with (OUT / f"{name}.csv").open("w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["ts_utc", "open", "high", "low", "close", "volume"])
        for i in range(len(bars)):
            w.writerow([bars.ts[i].isoformat(), f"{bars.open[i]:.6f}", f"{bars.high[i]:.6f}", f"{bars.low[i]:.6f}",
                        f"{bars.close[i]:.6f}", f"{bars.volume[i]:.0f}"])


def random_walk(n: int = 300, seed: int = 42):  # type: ignore[no-untyped-def]
    """Alltagsähnliche Reihe mit festem Startwert: Zufallsbewegung mit leichtem Wellenanteil."""
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, n) + 0.004 * np.sin(np.arange(n) / 11)))
    anchors = [(i, float(c)) for i, c in enumerate(close)]
    vol = (1_000_000 * (1 + 0.3 * rng.standard_normal(n).clip(-2, 2))).tolist()
    return path(anchors, vol, spread=0.006)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, anchors in ANCHORS.items():
        write(name, path(anchors, flat_volume(anchors[-1][0] + 1)))
    write("zufallsreihe_seed42", random_walk())


if __name__ == "__main__":
    main()
