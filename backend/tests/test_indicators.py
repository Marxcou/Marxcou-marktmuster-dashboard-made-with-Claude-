"""Indikator-Formeln gegen bekannte Referenzwerte und einfache analytische Fälle."""
import numpy as np
import pytest

from app.analysis import indicators as ind


def arr(*x: float) -> np.ndarray:
    return np.array(x, dtype=float)


def test_sma_reference():
    out = ind.sma(arr(1, 2, 3, 4, 5), 3)
    assert np.isnan(out[:2]).all()
    assert out[2:].tolist() == [2, 3, 4]


def test_sma_too_short_is_all_nan():
    assert np.isnan(ind.sma(arr(1, 2), 3)).all()


def test_ema_seed_is_sma_then_recursion():
    out = ind.ema(arr(1, 2, 3, 4, 5, 6), 3)  # alpha = 0.5, Start = SMA(1,2,3) = 2
    assert np.isnan(out[:2]).all()
    assert out[2:].tolist() == [2, 3, 4, 5]


def test_rsi_wilder_reference_values():
    # Beispielreihe der StockCharts-Erklärung zum RSI (Wilder-Glättung, Periode 14)
    close = arr(44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28,
                46.28, 46.00, 46.03, 46.41, 46.22, 45.64)
    out = ind.rsi(close, 14)
    assert np.isnan(out[:14]).all()
    assert out[14:].tolist() == pytest.approx([70.46, 66.25, 66.48, 69.35, 66.29, 57.92], abs=0.01)


def test_rsi_extremes():
    assert ind.rsi(np.arange(1, 30, dtype=float), 14)[-1] == 100.0
    assert ind.rsi(np.arange(30, 1, -1, dtype=float), 14)[-1] == 0.0
    assert ind.rsi(np.full(30, 5.0), 14)[-1] == 50.0


def test_macd_on_linear_ramp_converges_to_lag_difference():
    # EMA einer Rampe mit Steigung 1 hinkt (n-1)/2 hinterher, also MACD -> (26-12)/2 = 7, Histogramm -> 0
    line, sig, hist = ind.macd(np.arange(1, 400, dtype=float), 12, 26, 9)
    assert np.isnan(line[:25]).all() and not np.isnan(line[25])
    assert line[-1] == pytest.approx(7.0, abs=1e-6)
    assert sig[-1] == pytest.approx(7.0, abs=1e-6)
    assert hist[-1] == pytest.approx(0.0, abs=1e-6)
    assert np.isnan(sig[:25 + 8]).all() and not np.isnan(sig[33])


def test_bollinger_population_std():
    mid, up, lo = ind.bollinger(arr(1, 2, 3), 3, 2.0)
    sd = (2 / 3) ** 0.5
    assert mid[2] == 2 and up[2] == pytest.approx(2 + 2 * sd) and lo[2] == pytest.approx(2 - 2 * sd)


def test_bollinger_constant_series_has_zero_width():
    mid, up, lo = ind.bollinger(np.full(30, 7.0), 20, 2.0)
    assert up[-1] == lo[-1] == mid[-1] == 7.0
