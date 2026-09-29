"""Prognose-Kern (reines numpy): Korridor, Determinismus, ARIMA-Schätzung, Erstberührung, Backtest ohne Vorgriff.
Synthetische Reihen mit bekannten Eigenschaften (Zufallsreihen mit festem Seed)."""
import math
from datetime import datetime

import numpy as np
import pytest

from app.analysis import forecast as fc


def gbm(n=1300, sigma=0.015, drift=0.0, seed=1):
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(drift, sigma, n)))


def ar1_series(n=1300, phi=-0.6, sigma=0.01, seed=2):
    rng = np.random.default_rng(seed)
    r = np.zeros(n)
    e = rng.normal(0, sigma, n)
    for t in range(1, n):
        r[t] = phi * r[t - 1] + e[t]
    return 100 * np.exp(np.cumsum(r))


@pytest.mark.parametrize("method", [fc.PRIMARY, fc.COMPARISON])
def test_quantiles_are_ordered_and_widen(method):
    q = fc.forecast(method, gbm(), seed=3).quantiles
    assert q.shape == (7, fc.HORIZON)
    assert np.all(np.diff(q, axis=0) >= 0)  # 2,5 <= 10 <= ... <= 97,5 je Schritt
    width = q[6] - q[0]
    assert width[-1] > width[0] * 2  # Unsicherheit wächst mit dem Horizont


def test_bootstrap_is_deterministic_per_seed():
    close = gbm()
    a = fc.forecast(fc.PRIMARY, close, seed=7).quantiles
    b = fc.forecast(fc.PRIMARY, close, seed=7).quantiles
    c = fc.forecast(fc.PRIMARY, close, seed=8).quantiles
    assert np.array_equal(a, b) and not np.array_equal(a, c)


def test_bootstrap_removes_past_trend():
    close = gbm(drift=0.004)  # starker Anstieg (~+170 % über 250 Tage)
    q = fc.forecast(fc.PRIMARY, close, seed=1).quantiles
    assert abs(q[3, -1] / close[-1] - 1) < 0.02  # Median bleibt nahe am letzten Kurs
    with_drift = fc.forecast(fc.PRIMARY, close, params={**fc.DEFAULT_PARAMS[fc.PRIMARY], "remove_drift": False},
                             seed=1).quantiles
    assert with_drift[3, -1] / close[-1] > 1.05


def test_too_few_bars_raise():
    with pytest.raises(ValueError):
        fc.forecast(fc.PRIMARY, gbm(n=100))


def test_ar1_fit_recovers_phi():
    r = fc.log_returns(ar1_series(n=3000, phi=0.5))
    _, phi, sigma = fc.fit_ar1(r)
    assert phi == pytest.approx(0.5, abs=0.05)
    assert sigma == pytest.approx(0.01, rel=0.1)


def test_arima_band_width_matches_random_walk():
    close = gbm(n=3000, sigma=0.01)
    q = fc.arima_quantiles(close, 20, {"lookback_bars": 2999})
    width_log = math.log(q[6, -1] / q[0, -1])
    assert width_log == pytest.approx(2 * 1.96 * 0.01 * math.sqrt(20), rel=0.12)


def test_first_passage_counts_first_touch():
    paths = np.array([
        [100, 106, 90],   # oben zuerst
        [94, 110, 110],   # unten zuerst
        [100, 101, 102],  # keins
        [100, 100, 105],  # oben (am Niveau zählt)
    ], dtype=float)
    fp = fc.first_passage(paths, upper=105, lower=95)
    assert (fp.upper_first, fp.lower_first, fp.neither) == (0.5, 0.25, 0.25)


def test_future_weekdays_skip_weekend():
    from datetime import UTC, datetime
    fri = datetime(2026, 9, 25, tzinfo=UTC)
    days = fc.future_weekdays(fri, 3)
    assert [d.day for d in days] == [28, 29, 30]


def test_backtest_uses_no_future_data(monkeypatch):
    close = gbm(n=400)
    seen = []
    real = fc.forecast

    def spy(method, train, horizon, params, seed=0):
        seen.append(len(train))
        return real(method, train, horizon, params, seed)

    monkeypatch.setattr(fc, "forecast", spy)
    res = fc.rolling_backtest(fc.COMPARISON, close)
    assert res.sample_size == len(seen) > 0
    assert seen == [o + 1 for o in res.origins]  # nur Kerzen bis zum Ursprung
    assert res.origins[-1] + 20 <= len(close) - 1  # Ergebnis liegt in der gespeicherten Historie


def test_backtest_random_walk_is_not_better_than_naive():
    res = fc.rolling_backtest(fc.PRIMARY, gbm())
    h = res.at(20)
    assert h is not None and h.sample_size >= 30
    assert h.better_than_naive is False
    assert 0.65 <= h.coverage[0.8] <= 0.95
    assert h.pinball_model < h.pinball_naive


def test_backtest_detects_skill_on_predictable_series():
    res = fc.rolling_backtest(fc.COMPARISON, ar1_series(phi=-0.6), bt={"horizons": [1, 5, 20]})
    h1 = res.at(1)
    assert h1 is not None and h1.better_than_naive is True and h1.skill is not None and h1.skill > 0.05
    assert h1.dm_p_value is not None and h1.dm_p_value < 0.05


def test_backtest_small_sample_gives_no_verdict():
    res = fc.rolling_backtest(fc.COMPARISON, gbm(n=320))
    h = res.at(20)
    assert h is not None and h.sample_size < 30 and h.better_than_naive is None


def test_backtest_without_enough_bars_is_empty():
    assert fc.rolling_backtest(fc.COMPARISON, gbm(n=260)).sample_size == 0


def test_diebold_mariano():
    assert fc.diebold_mariano(np.full(50, -1.0), 0) is None  # keine Varianz
    rng = np.random.default_rng(0)
    d = rng.normal(-0.5, 1, 200)
    p = fc.diebold_mariano(d, 0)
    assert p is not None and p < 0.001
    p_pos = fc.diebold_mariano(-d, 0)
    assert p_pos is not None and p_pos > 0.999


def test_example_paths_follow_end_value_percentiles():
    f = fc.forecast(fc.PRIMARY, gbm(), seed=5)
    assert f.paths is not None
    picked = fc.example_path_indices(f.paths)
    assert [p for p, _ in picked] == list(fc.EXAMPLE_PERCENTILES)
    ends = [float(f.paths[k, -1]) for _, k in picked]
    assert ends == sorted(ends)  # 10. bis 90. Perzentil aufsteigend
    all_ends = f.paths[:, -1]
    for (p, _), end in zip(picked, ends, strict=True):
        assert (all_ends <= end).mean() == pytest.approx(p / 100, abs=0.01)
    # Median-Beispielpfad endet am Median der Endwerte, also in der Mitte des Korridors
    assert ends[2] == pytest.approx(f.quantiles[3, -1], rel=1e-3)


def test_example_path_rows_are_real_simulated_paths():
    f = fc.forecast(fc.PRIMARY, gbm(), seed=5)
    assert f.paths is not None
    ts = fc.future_weekdays(datetime(2026, 9, 25), fc.HORIZON)
    rows = fc.example_path_rows(f.paths, ts)
    assert len(rows) == 5 and all(len(r["steps"]) == fc.HORIZON for r in rows)
    k = dict(fc.example_path_indices(f.paths))[70]
    row = next(r for r in rows if r["percentile"] == 70)
    assert [s["close"] for s in row["steps"]] == [round(float(v), 4) for v in f.paths[k]]
    assert row["steps"][0]["ts"] == ts[0].isoformat()
