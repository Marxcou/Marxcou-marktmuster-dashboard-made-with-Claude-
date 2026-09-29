"""Muster-Engine: synthetische Kursreihen mit bekanntem Ergebnis (Stützpunkte = erwartete Wendepunkte)."""
import dataclasses

import numpy as np
import pytest

from app.analysis.engine import build_context, detect
from app.analysis.params import default_params, params_hash
from app.analysis.patterns.common import Detection, score_band, score_ge, score_le
from app.analysis.pivots import zigzag
from app.analysis.series import Bars, atr
from app.grundregeln import find_forbidden
from tests.synthetic import flat_volume, path

# Mustertyp -> (Stützpunkte, erwarteter Beginn, erwartetes Ende, erwarteter Status, Kerze der Bestätigung)
CASES: dict[str, tuple[list[tuple[int, float]], int, int, str, int | None]] = {
    "doppelboden": ([(0, 120), (30, 100), (45, 110), (60, 100.3), (80, 118), (100, 125)], 30, 60, "bestaetigt", 72),
    "doppelhoch": ([(0, 80), (30, 100), (45, 90), (60, 99.7), (80, 82), (100, 78)], 30, 60, "bestaetigt", 72),
    "kopf_schulter": ([(0, 80), (20, 100), (30, 92), (45, 108), (60, 92.5), (75, 100.5), (95, 82), (110, 80)],
                      20, 75, "bestaetigt", 84),
    "kopf_schulter_invers": ([(0, 120), (20, 100), (30, 108), (45, 92), (60, 107.5), (75, 99.5), (95, 118),
                              (110, 120)], 20, 75, "bestaetigt", 84),
    "dreieck_aufsteigend": ([(0, 120), (25, 90), (35, 110), (45, 97), (55, 110), (65, 103), (75, 110), (80, 107),
                             (90, 118), (100, 120)], 35, 80, "bestaetigt", 83),
    "dreieck_absteigend": ([(0, 80), (25, 110), (35, 90), (45, 103), (55, 90), (65, 97), (75, 90), (80, 93),
                            (90, 82), (100, 80)], 35, 80, "bestaetigt", 83),
    "dreieck_symmetrisch": ([(0, 70), (25, 110), (35, 90), (45, 106), (55, 94), (65, 102), (75, 97), (80, 100),
                             (90, 108), (100, 110)], 25, 75, "bestaetigt", 79),
    "keil_steigend": ([(0, 120), (25, 90), (35, 100), (45, 95), (55, 105), (65, 101), (75, 109), (80, 106),
                       (90, 95), (100, 92)], 25, 75, "bestaetigt", 81),
    "keil_fallend": ([(0, 80), (25, 110), (35, 100), (45, 105), (55, 95), (65, 99), (75, 91), (80, 94), (90, 105),
                      (100, 108)], 25, 75, "bestaetigt", 81),
    "flagge_aufwaerts": ([(0, 100), (40, 100), (48, 120), (60, 116), (62, 117), (70, 126), (80, 128)],
                         41, 61, "bestaetigt", 62),
    "flagge_abwaerts": ([(0, 120), (40, 120), (48, 100), (60, 104), (62, 103), (70, 94), (80, 92)],
                        41, 61, "bestaetigt", 62),
    "wimpel_aufwaerts": ([(0, 100), (40, 100), (48, 120), (50, 116), (52, 119.5), (54, 116.8), (56, 118.8),
                          (58, 117.4), (60, 118.3), (62, 117.8), (70, 126), (80, 128)], 41, 63, "bestaetigt", 64),
}


def mirror(anchors: list[tuple[int, float]]) -> list[tuple[int, float]]:
    return [(i, 200 - p) for i, p in anchors]


# Gespiegelt; die Kanal-Regression reagiert auf den prozentualen Spread, daher endet sie eine Kerze früher
CASES["wimpel_abwaerts"] = (mirror(CASES["wimpel_aufwaerts"][0]), 41, 62, "bestaetigt", 63)


def find(dets: list[Detection], ptype: str, start: int, end: int) -> Detection:
    hits = [d for d in dets if d.pattern_type == ptype and abs(d.start_idx - start) <= 1 and abs(d.end_idx - end) <= 1]
    assert hits, f"{ptype} {start}-{end} nicht gefunden: {[(d.pattern_type, d.start_idx, d.end_idx) for d in dets]}"
    return hits[0]


@pytest.mark.parametrize("ptype", sorted(CASES))
def test_known_pattern_is_detected(ptype: str) -> None:
    anchors, start, end, status, confirmed = CASES[ptype]
    det = find(detect(path(anchors), "1d").detections, ptype, start, end)
    assert det.status == status
    assert det.confirmed_idx == confirmed


@pytest.mark.parametrize("ptype", sorted(CASES))
def test_explanation_duty_for_every_pattern_type(ptype: str) -> None:
    """Grundregel 3: Name, Lage, Kriterien mit tatsächlichen Werten, Konfidenz mit Aufschlüsselung,
    mindestens zwei Szenarien mit Niveaus. Die Trefferquote hängt die API aus backtest_runs an."""
    anchors, start, end, _, _ = CASES[ptype]
    det = find(detect(path(anchors, flat_volume(anchors[-1][0] + 1)), "1d").detections, ptype, start, end)
    assert det.name and det.key_points and det.lines
    assert det.start_idx <= min(k.idx for k in det.key_points) and det.formed_idx >= det.end_idx - 1
    required = [c for c in det.criteria if c.required]
    assert len(required) >= 3 and all(c.passed for c in required)
    for c in det.criteria:
        assert c.actual_text and c.rule and 0 <= c.sub_score <= 1 and c.weight > 0
        assert c.actual is not None
    assert abs(sum(float(b["contribution"]) for b in det.breakdown) - det.confidence) < 1e-3
    assert abs(sum(float(b["weight"]) for b in det.breakdown) - 1) < 1e-3
    assert 0 < det.confidence <= 1
    assert len(det.scenarios) >= 2
    assert all(s.trigger_level > 0 and s.trigger_rule and s.description for s in det.scenarios)
    assert det.confirmation_level > 0 and det.invalidation_level > 0
    texts = [det.explanation, det.status_reason, *(c.actual_text + c.rule + c.name for c in det.criteria),
             *(s.title + s.trigger_rule + s.description for s in det.scenarios)]
    assert find_forbidden(" ".join(texts)) == []
    assert det.explanation.startswith(det.name) and " bis " in det.explanation


def test_double_bottom_values_in_explanation() -> None:
    det = find(detect(path(CASES["doppelboden"][0]), "1d").detections, "doppelboden", 30, 60)
    crit = {c.key: c for c in det.criteria}
    # Tiefs 99,80 (100 − 0,2 %) und 100,10 (100,3 − 0,2 %, gerundet)
    assert crit["extrem_abweichung"].actual == pytest.approx(0.3, abs=0.01)
    assert "Tief 1: 99,80 am 31.01.2024" in crit["extrem_abweichung"].actual_text
    assert det.confirmation_level == pytest.approx(110.22, abs=0.01)  # Zwischenhoch = Nackenlinie
    assert det.invalidation_level == pytest.approx(99.8 * 0.985, abs=0.01)
    assert [s.kind for s in det.scenarios] == ["bestaetigung", "scheitern"]


def test_symmetric_triangle_has_breakout_scenarios_and_direction() -> None:
    anchors, start, end, _, _ = CASES["dreieck_symmetrisch"]
    det = find(detect(path(anchors), "1d").detections, "dreieck_symmetrisch", start, end)
    assert det.direction == "offen" and det.breakout_direction == "aufwärts"
    assert [s.kind for s in det.scenarios] == ["ausbruch_oben", "ausbruch_unten"]


def test_too_different_lows_are_no_double_bottom() -> None:
    dets = detect(path([(0, 120), (30, 100), (45, 110), (60, 104), (80, 118), (100, 125)]), "1d").detections
    assert not [d for d in dets if d.pattern_type == "doppelboden"]


def test_head_below_shoulder_is_no_head_and_shoulders() -> None:
    anchors = [(0, 80), (20, 100), (30, 92), (45, 99), (60, 92.5), (75, 100.5), (95, 82), (110, 80)]
    assert not [d for d in detect(path(anchors), "1d").detections if d.pattern_type == "kopf_schulter"]


def test_straight_trend_has_no_patterns() -> None:
    result = detect(path([(0, 100), (200, 160)]), "1d")
    assert result.detections == [] and result.zones == []


def test_double_bottom_invalidation() -> None:
    anchors = [(0, 120), (30, 100), (45, 110), (60, 100.3), (70, 104), (85, 90), (100, 88)]
    det = find(detect(path(anchors), "1d").detections, "doppelboden", 30, 60)
    assert det.status == "ungueltig" and det.confirmed_idx is None
    bars = path(anchors)
    assert det.invalidated_idx is not None and bars.close[det.invalidated_idx] < det.invalidation_level
    assert "Ungültigkeitsniveau" in det.status_reason


def test_double_bottom_still_forming_at_series_end() -> None:
    anchors = [(0, 120), (30, 100), (45, 110), (60, 100.3), (70, 106)]
    det = find(detect(path(anchors), "1d").detections, "doppelboden", 30, 60)
    assert det.status == "in_bildung" and det.status_idx is None
    assert "(Wert am" not in det.scenarios[0].trigger_rule


def test_double_bottom_expires_without_confirmation() -> None:
    anchors = [(0, 120), (30, 100), (45, 110), (60, 100.3), (70, 106), (80, 103), (90, 107), (100, 104)]
    det = find(detect(path(anchors), "1d").detections, "doppelboden", 30, 60)
    assert det.status == "ungueltig" and "Fristende" in det.status_reason


def test_detection_is_deterministic() -> None:
    bars = path(CASES["kopf_schulter"][0])
    a, b = detect(bars, "1d"), detect(bars, "1d")
    assert [dataclasses.asdict(d) for d in a.detections] == [dataclasses.asdict(d) for d in b.detections]
    assert params_hash(default_params()) == params_hash(default_params())


def test_params_change_hash_and_result() -> None:
    params = default_params()
    params["doppel"]["max_extrem_abweichung_pct"] = 0.1
    assert params_hash(params) != params_hash(default_params())
    dets = detect(path(CASES["doppelboden"][0]), "1d", params).detections
    assert not [d for d in dets if d.pattern_type == "doppelboden"]


def test_pivots_are_confirmed_later_and_without_lookahead() -> None:
    bars = path(CASES["kopf_schulter"][0])
    ctx = build_context(bars, "1d")
    assert all(p.confirmed_idx > p.idx for p in ctx.pivots)
    cut = 70
    short = Bars(bars.ts[: cut + 1], bars.open[: cut + 1], bars.high[: cut + 1], bars.low[: cut + 1],
                 bars.close[: cut + 1], bars.volume[: cut + 1])
    pp = default_params()["pivots"]
    short_pivots = zigzag(short, atr(short, int(pp["atr_periode"])), pp["atr_faktor"], pp["min_bewegung_pct"])
    assert short_pivots == [p for p in ctx.pivots if p.confirmed_idx <= cut]


def test_volume_criterion_only_with_volume() -> None:
    anchors, start, end, _, _ = CASES["doppelboden"]
    no_vol = find(detect(path(anchors), "1d").detections, "doppelboden", start, end)
    assert "volumen" not in {c.key for c in no_vol.criteria}
    n = anchors[-1][0] + 1
    vol = [2_000_000.0 if 28 <= i <= 32 else 1_000_000.0 for i in range(n)]
    with_vol = find(detect(path(anchors, vol), "1d").detections, "doppelboden", start, end)
    v = {c.key: c for c in with_vol.criteria}["volumen"]
    assert not v.required and v.passed and v.actual == pytest.approx(0.5)


def test_support_and_resistance_zones() -> None:
    anchors = [(0, 110), (15, 100), (30, 120), (45, 100.5), (60, 119.5), (75, 100.2), (90, 120.3), (105, 110)]
    zones = detect(path(anchors), "1d").zones
    kinds = {z.kind: z for z in zones}
    assert set(kinds) == {"unterstuetzung", "widerstand"}
    sup, res = kinds["unterstuetzung"], kinds["widerstand"]
    assert len(sup.touches) == 3 and 99.5 < sup.lower <= sup.upper < 100.5
    assert len(res.touches) == 3 and 119.5 < res.lower <= res.upper < 120.6
    assert sup.explanation.startswith("Unterstützungszone zwischen")
    assert abs(sum(float(b["contribution"]) for b in sup.breakdown) - sup.confidence) < 1e-3


def test_too_few_bars() -> None:
    result = detect(path([(0, 100), (30, 110)]), "1d")
    assert result.detections == [] and result.pivots == []


def test_atr_wilder() -> None:
    bars = path([(0, 100), (20, 100)], spread=0.01)
    a = atr(bars, 14)
    assert a[0] == pytest.approx(2.0) and a[-1] == pytest.approx(2.0)


def test_score_functions() -> None:
    assert score_le(0, 0, 1.5) == 1 and score_le(1.5, 0, 1.5) == 0 and score_le(0.75, 0, 1.5) == 0.5
    assert score_ge(8, 8, 3) == 1 and score_ge(3, 8, 3) == 0 and score_ge(5.5, 8, 3) == 0.5
    assert score_band(50, 20, 80, 10, 120) == 1 and score_band(15, 20, 80, 10, 120) == 0.5


def test_random_walk_runs_fast_and_consistent() -> None:
    rng = np.random.default_rng(7)
    n = 1300
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.015, n)))
    open_ = np.concatenate(([close[0]], close[:-1]))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.005, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.005, n)))
    bars = path([(0, 1), (n - 1, 1)])
    bars = Bars(bars.ts, open_, high, low, close, rng.uniform(1e6, 2e6, n))
    result = detect(bars, "1d")
    assert result.detections
    for d in result.detections:
        assert all(c.passed for c in d.criteria if c.required)
        assert d.status in ("in_bildung", "bestaetigt", "ungueltig")
        if d.confirmed_idx is not None:
            assert d.confirmed_idx > d.end_idx
