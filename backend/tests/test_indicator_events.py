"""Ereigniserkennung auf synthetischen Kursreihen mit bekanntem Ergebnis."""
from datetime import UTC, datetime, timedelta

import numpy as np

from app.analysis import events as ev
from app.analysis import moves as mv

T0 = datetime(2025, 1, 1, tzinfo=UTC)


def series(close, volume=None, spread=0.001) -> ev.Series:
    c = np.asarray(close, dtype=float)
    n = len(c)
    vol = np.full(n, np.nan) if volume is None else np.asarray(volume, dtype=float)
    return ev.Series(ts=[T0 + timedelta(days=i) for i in range(n)], open=c, high=c * (1 + spread),
                     low=c * (1 - spread), close=c, volume=vol, timeframe="1d", currency="USD")


def of_type(events, typ):
    return [e for e in events if e.type == typ]


def test_golden_and_death_cross_found_exactly_once_each():
    down = np.linspace(200, 100, 260)
    up = np.linspace(100, 260, 120)
    down2 = np.linspace(260, 60, 250)
    s = series(np.concatenate([down, up, down2]))
    events = ev.detect_all(s)
    golden, death = of_type(events, "golden_cross"), of_type(events, "death_cross")
    assert len(golden) == 1 and len(death) == 1
    g, d = golden[0], death[0]
    assert g.index < d.index
    # Erklärung: die Kriterien tragen die tatsächlichen Werte, die Vorkerze lag auf der anderen Seite
    assert g.values["sma_fast_prev"] <= g.values["sma_slow_prev"] and g.values["sma_fast"] > g.values["sma_slow"]
    assert d.values["sma_fast_prev"] >= d.values["sma_slow_prev"] and d.values["sma_fast"] < d.values["sma_slow"]
    assert g.direction == "up" and d.direction == "down"
    assert g.params == ev.PARAMS["cross"]
    assert all(c["passed"] for c in g.criteria) and len(g.criteria) == 2


def test_no_cross_without_enough_bars():
    assert of_type(ev.detect_all(series(np.linspace(100, 50, 150))), "golden_cross") == []


def _divergence_closes(second_drop_speed: int) -> np.ndarray:
    flat = np.full(40, 120.0)
    crash = np.linspace(120, 100, 8)[1:]  # schneller Absturz, RSI sehr niedrig
    rebound = np.linspace(100, 112, 10)[1:]
    drift = np.linspace(112, 99, second_drop_speed + 1)[1:]  # zweites, tieferes Tief
    recovery = np.linspace(99, 115, 12)[1:]
    return np.concatenate([flat, crash, rebound, drift, recovery])


def test_bullish_rsi_divergence_detected_with_values():
    s = series(_divergence_closes(30), spread=0.0)
    found = of_type(ev.detect_all(s), "rsi_divergence")
    assert len(found) == 1
    e = found[0]
    assert e.direction == "up"
    p1, p2 = e.values["pivot1"], e.values["pivot2"]
    assert p2["price"] < p1["price"] and p2["rsi"] > p1["rsi"]
    assert e.confirmed_index == e.index + ev.PARAMS["rsi_divergence"]["pivot_window"]
    assert 5 <= e.values["bars_apart"] <= 60
    assert len(e.criteria) == 4 and all(c["passed"] for c in e.criteria)
    assert "höheres Tief" in e.summary


def test_bearish_rsi_divergence_is_mirror_image():
    s = series(400 - _divergence_closes(30), spread=0.0)
    found = [e for e in ev.detect_all(s) if e.type == "rsi_divergence" and e.direction == "down"]
    assert len(found) == 1
    p1, p2 = found[0].values["pivot1"], found[0].values["pivot2"]
    assert p2["price"] > p1["price"] and p2["rsi"] < p1["rsi"]


def test_no_divergence_when_second_low_is_not_lower():
    flat = np.full(40, 120.0)
    leg1 = np.linspace(120, 100, 8)[1:]
    reb = np.linspace(100, 112, 10)[1:]
    leg2 = np.linspace(112, 103, 20)[1:]  # höheres Tief im Kurs: keine Divergenz im Sinne der Regel
    s = series(np.concatenate([flat, leg1, reb, leg2, np.linspace(103, 115, 12)]), spread=0.0)
    assert of_type(ev.detect_all(s), "rsi_divergence") == []


def test_bollinger_breakout_only_on_first_close_outside():
    close = np.array([100.1, 99.9] * 20 + [105.0, 105.5])
    s = series(close)
    found = of_type(ev.detect_all(s), "bb_breakout")
    assert [(e.index, e.direction) for e in found] == [(40, "up")]
    e = found[0]
    assert e.values["close"] == 105.0 and e.values["close"] > e.values["upper"] >= e.values["middle"]
    assert e.values["close_prev"] <= e.values["upper"]  # Vorkerze war innerhalb
    down = of_type(ev.detect_all(series(np.array([100.1, 99.9] * 20 + [95.0]))), "bb_breakout")
    assert [(e.index, e.direction) for e in down] == [(40, "down")]


def test_volume_spike_and_negatives():
    vol = np.array([1000, 1100] * 15 + [5000], dtype=float)
    found = of_type(ev.detect_all(series(np.full(31, 100.0), volume=vol)), "volume_spike")
    assert len(found) == 1 and found[0].index == 30 and found[0].direction is None
    assert found[0].values["ratio"] > 4 and found[0].values["z"] >= 3
    # zu geringer Anstieg: kein Ereignis
    vol2 = np.array([1000, 1100] * 15 + [1400], dtype=float)
    assert of_type(ev.detect_all(series(np.full(31, 100.0), volume=vol2)), "volume_spike") == []
    # ohne Volumen der Quelle: keine Ereignisse, keine Erfindung
    assert of_type(ev.detect_all(series(np.full(31, 100.0))), "volume_spike") == []


def test_every_event_carries_explanation_and_neutral_language():
    from app.grundregeln import find_forbidden
    rng = np.random.default_rng(7)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 900)))
    vol = rng.lognormal(10, 0.5, 900)
    events = ev.detect_all(series(close, volume=vol, spread=0.004))
    assert {e.type for e in events} >= {"bb_breakout", "volume_spike"}
    for e in events:
        assert e.criteria and all({"name", "rule", "required", "actual", "passed"} <= set(c) for c in e.criteria)
        assert e.params and e.values and e.title and e.summary
        assert find_forbidden(f"{e.title} {e.summary} " + " ".join(c["rule"] + c["name"] for c in e.criteria)) == []


def test_detection_is_deterministic():
    rng = np.random.default_rng(3)
    s = series(100 * np.exp(np.cumsum(rng.normal(0, 0.02, 500))), volume=rng.lognormal(10, 0.4, 500))
    a = [(e.type, e.direction, e.index, e.summary) for e in ev.detect_all(s)]
    assert a == [(e.type, e.direction, e.index, e.summary) for e in ev.detect_all(s)]


def test_notable_move_detects_outlier_return():
    ret = np.array([0.005, -0.005] * 40)
    close = 100 * np.cumprod(1 + np.concatenate([[0], ret, [-0.05], [0.005]]))
    moves = mv.detect_moves(series(close))
    assert len(moves) == 1
    m = moves[0]
    assert m.index == 81 and m.return_pct < -4.9 and m.return_z is not None and m.return_z < -3
    assert m.reasons == ["return_z"] and m.volume_z is None


def test_notable_move_by_volume_only():
    close = 100 * np.cumprod(1 + np.array([0] + [0.005, -0.005] * 40 + [0.005]))
    vol = np.array([1000, 1100] * 40 + [1000, 9000], dtype=float)
    moves = mv.detect_moves(series(close, volume=vol))
    assert [m.reasons for m in moves] == [["volume_z"]]
