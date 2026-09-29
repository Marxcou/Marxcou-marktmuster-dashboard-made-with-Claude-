"""Technische Indikatoren mit dokumentierten Formeln. Alle Funktionen nehmen ein float64-Array und liefern ein
Array gleicher Länge; Werte vor dem ersten gültigen Punkt sind NaN (Warm-up)."""
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

F64 = np.ndarray  # dtype float64


def sma(x: F64, n: int) -> F64:
    """Arithmetisches Mittel der letzten n Werte."""
    out = np.full(len(x), np.nan)
    if n < 1 or len(x) < n:
        return out
    out[n - 1:] = sliding_window_view(x, n).mean(axis=1)
    return out


def ema(x: F64, n: int) -> F64:
    """Exponentieller Durchschnitt, alpha = 2/(n+1). Startwert (bei Index n-1) ist der SMA der ersten n Werte.
    Enthält x führende NaN (z. B. MACD-Linie), beginnt die Reihe nach dem ersten gültigen Block von n Werten."""
    out = np.full(len(x), np.nan)
    valid = np.flatnonzero(~np.isnan(x))
    if n < 1 or len(valid) < n:
        return out
    first = int(valid[0])
    start = first + n - 1
    alpha = 2.0 / (n + 1)
    out[start] = x[first:start + 1].mean()
    for i in range(start + 1, len(x)):
        out[i] = alpha * x[i] + (1 - alpha) * out[i - 1]
    return out


def rsi(close: F64, n: int = 14) -> F64:
    """RSI nach Wilder: RS = geglätteter Durchschnittsgewinn / geglätteter Durchschnittsverlust (Glättung
    (alt*(n-1)+neu)/n, Start = einfacher Mittelwert der ersten n Änderungen), RSI = 100 - 100/(1+RS).
    Ohne Verluste ist der RSI 100, ohne jede Änderung 50."""
    out = np.full(len(close), np.nan)
    if n < 1 or len(close) <= n:
        return out
    delta = np.diff(close)
    gain, loss = np.where(delta > 0, delta, 0.0), np.where(delta < 0, -delta, 0.0)
    avg_g, avg_l = gain[:n].mean(), loss[:n].mean()

    def value(g: float, lo: float) -> float:
        if lo == 0:
            return 50.0 if g == 0 else 100.0
        return 100.0 - 100.0 / (1.0 + g / lo)

    out[n] = value(avg_g, avg_l)
    for i in range(n, len(delta)):
        avg_g = (avg_g * (n - 1) + gain[i]) / n
        avg_l = (avg_l * (n - 1) + loss[i]) / n
        out[i + 1] = value(avg_g, avg_l)
    return out


def macd(close: F64, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[F64, F64, F64]:
    """MACD-Linie = EMA(fast) - EMA(slow); Signal = EMA(signal) der MACD-Linie; Histogramm = MACD - Signal."""
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def bollinger(close: F64, n: int = 20, k: float = 2.0) -> tuple[F64, F64, F64]:
    """Mittelband = SMA(n); Bänder = Mittelband +/- k * Standardabweichung (Grundgesamtheit, ddof=0) der
    letzten n Schlusskurse. Rückgabe: (mittel, oben, unten)."""
    mid = sma(close, n)
    std = np.full(len(close), np.nan)
    if n >= 1 and len(close) >= n:
        std[n - 1:] = sliding_window_view(close, n).std(axis=1)
    return mid, mid + k * std, mid - k * std


def rolling_std(x: F64, n: int, ddof: int = 0) -> F64:
    out = np.full(len(x), np.nan)
    if len(x) >= n > ddof:
        out[n - 1:] = sliding_window_view(x, n).std(axis=1, ddof=ddof)
    return out
