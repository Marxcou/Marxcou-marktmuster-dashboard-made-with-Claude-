"""Statistische Prognosen als Quantil-Korridor und rollierender Backtest (reines numpy, ohne I/O).

Grundregel 4: Ergebnis ist immer ein Satz Quantile je Schritt. Der Median (50-%-Quantil) wird als "mittlerer Verlauf"
nur innerhalb dieses Korridors gezeigt, nie allein; Beispielpfade aus der Simulation ebenso. Alles ist deterministisch:
der Zufalls-Seed der Simulation hängt nur vom Datenstand ab (gleiche Kerzen -> gleicher Korridor).

Methoden:
- monte_carlo_block_bootstrap (Hauptmethode): zieht Blöcke zusammenhängender historischer Tagesrenditen und setzt
  sie zu vielen möglichen Pfaden zusammen. Blöcke erhalten kurzfristige Abhängigkeiten (z. B. Phasen hoher
  Schwankung). Der historische Durchschnittstrend wird entfernt, damit ein vergangener Anstieg oder Rückgang nicht
  fortgeschrieben wird.
- arima_1_1_0 (Vergleich): AR(1) auf Tagesrenditen der Log-Kurse (= ARIMA(1,1,0) mit Konstante), geschätzt per
  Kleinste-Quadrate, Normalverteilung der Fehler.
"""
import hashlib
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]

ALGO_VERSION = "forecast-1"
HORIZON = 20
MIN_BARS = 250
QUANTILES: tuple[float, ...] = (0.025, 0.10, 0.25, 0.50, 0.75, 0.90, 0.975)
QKEYS: tuple[str, ...] = ("2.5", "10", "25", "50", "75", "90", "97.5")
# Standardnormal-Quantile zu QUANTILES (für ARIMA, ohne scipy)
Z: tuple[float, ...] = (-1.959964, -1.281552, -0.674490, 0.0, 0.674490, 1.281552, 1.959964)
BANDS: list[dict[str, Any]] = [
    {"level": 0.5, "lower": "25", "upper": "75"},
    {"level": 0.8, "lower": "10", "upper": "90"},
    {"level": 0.95, "lower": "2.5", "upper": "97.5"},
]
BAND_IDX = {0.5: (2, 4), 0.8: (1, 5), 0.95: (0, 6)}

PRIMARY = "monte_carlo_block_bootstrap"
COMPARISON = "arima_1_1_0"

DEFAULT_PARAMS: dict[str, dict[str, Any]] = {
    PRIMARY: {"lookback_bars": 750, "block_length": 10, "paths": 4000, "remove_drift": True},
    COMPARISON: {"lookback_bars": 750},
}
BACKTEST_PARAMS: dict[str, Any] = {
    "min_train_bars": MIN_BARS, "step_bars": 5, "horizons": [5, 10, 20], "max_origins": 300,
    "paths": 1000, "min_sample": 30, "alpha": 0.05,
}

COMMON_LIMITATIONS = [
    "Nutzt ausschließlich den bisherigen Kursverlauf; Nachrichten, Termine und Fundamentaldaten fließen nicht ein.",
    "Handelstage in der Zukunft sind vereinfacht als Werktage (Mo–Fr) gezählt; Feiertage sind nicht berücksichtigt.",
    "Die Bänder beschreiben die Schwankungsbreite unter der Annahme, dass die Vergangenheit repräsentativ ist. "
    "Seltene Ereignisse können außerhalb des 95-%-Bandes liegen.",
]

METHODS: dict[str, dict[str, Any]] = {
    PRIMARY: {
        "name": "Monte-Carlo-Simulation (Block-Bootstrap)",
        "description": (
            "Aus den Tagesrenditen der letzten {lookback_bars} Handelstage werden Blöcke von je {block_length} "
            "aufeinanderfolgenden Tagen zufällig gezogen und zu {paths} möglichen Kursverläufen zusammengesetzt. "
            "Je Tag werden daraus die Quantile 2,5/10/25/50/75/90/97,5 % bestimmt; sie bilden die Bänder "
            "50 %, 80 % und 95 %."
        ),
        "assumptions": [
            "Die künftigen Tagesrenditen ähneln in Verteilung und kurzfristiger Abhängigkeit denen des "
            "Rückblickzeitraums.",
            "Der durchschnittliche Trend des Rückblickzeitraums wird entfernt (kein Fortschreiben vergangener "
            "Anstiege oder Rückgänge).",
        ],
        "limitations": COMMON_LIMITATIONS,
    },
    COMPARISON: {
        "name": "ARIMA(1,1,0) auf Log-Kursen",
        "description": (
            "Autoregressives Modell erster Ordnung auf den Tagesrenditen der Log-Kurse der letzten {lookback_bars} "
            "Handelstage (Kleinste-Quadrate-Schätzung mit Konstante). Die Bänder folgen aus der Normalverteilung "
            "der aufsummierten Prognosefehler."
        ),
        "assumptions": [
            "Tagesrenditen hängen nur linear von der Vortagesrendite ab.",
            "Fehler sind normalverteilt mit konstanter Varianz; ein mittlerer Trend wird mitgeschätzt.",
        ],
        "limitations": [*COMMON_LIMITATIONS,
                        "Normalverteilte Fehler unterschätzen starke Kurssprünge meist."],
    },
}


def method_info(key: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    p = params or DEFAULT_PARAMS[key]
    m = METHODS[key]
    return {"key": key, "name": m["name"], "description": m["description"].format(**p),
            "assumptions": list(m["assumptions"]), "limitations": list(m["limitations"]), "params": dict(p)}


def seed_for(*parts: object) -> int:
    blob = "|".join(str(p) for p in parts).encode()
    return int.from_bytes(hashlib.sha256(blob).digest()[:4], "big")


def log_returns(close: FloatArray) -> FloatArray:
    return np.diff(np.log(close))


def future_weekdays(last: datetime, n: int) -> list[datetime]:
    out: list[datetime] = []
    d = last
    while len(out) < n:
        d = d + timedelta(days=1)
        if d.weekday() < 5:
            out.append(d)
    return out


# --- Methoden ---------------------------------------------------------------------------------------------------


def simulate_bootstrap(close: FloatArray, horizon: int, params: dict[str, Any], seed: int) -> FloatArray:
    """Pfade (paths x horizon) der Schlusskurse nach dem zirkulären Block-Bootstrap."""
    r = log_returns(close[-(int(params["lookback_bars"]) + 1):])
    if params.get("remove_drift", True):
        r = r - r.mean()
    n, block, paths = len(r), int(params["block_length"]), int(params["paths"])
    rng = np.random.default_rng(seed)
    nblocks = -(-horizon // block)
    starts = rng.integers(0, n, size=(paths, nblocks))
    idx = ((starts[:, :, None] + np.arange(block)) % n).reshape(paths, nblocks * block)[:, :horizon]
    return np.asarray(close[-1] * np.exp(np.cumsum(r[idx], axis=1)), dtype=np.float64)


def quantiles_from_paths(paths: FloatArray) -> FloatArray:
    """Quantile (len(QUANTILES) x horizon)."""
    return np.asarray(np.quantile(paths, QUANTILES, axis=0), dtype=np.float64)


def fit_ar1(r: FloatArray) -> tuple[float, float, float]:
    """Kleinste-Quadrate-Schätzung r_t = c + phi * r_{t-1} + e_t. Liefert (mu, phi, sigma)."""
    x, y = r[:-1], r[1:]
    xm, ym = x.mean(), y.mean()
    var_x = float(((x - xm) ** 2).sum())
    phi = float(((x - xm) * (y - ym)).sum() / var_x) if var_x > 0 else 0.0
    phi = max(-0.99, min(0.99, phi))
    c = ym - phi * xm
    resid = y - c - phi * x
    sigma = float(np.sqrt((resid**2).sum() / max(1, len(y) - 2)))
    mu = float(c / (1 - phi))
    return mu, phi, sigma


def arima_quantiles(close: FloatArray, horizon: int, params: dict[str, Any]) -> FloatArray:
    r = log_returns(close[-(int(params["lookback_bars"]) + 1):])
    mu, phi, sigma = fit_ar1(r)
    last_r = float(r[-1])
    ks = np.arange(1, horizon + 1)
    mean_r = mu + phi**ks * (last_r - mu)
    mean_cum = np.cumsum(mean_r)
    # Beitrag des Fehlers e_{T+j} zur Summe bis h: psi_j = (1 - phi^(h-j+1)) / (1 - phi)
    var_cum = np.empty(horizon)
    for h in range(1, horizon + 1):
        j = np.arange(1, h + 1)
        psi = (1 - phi ** (h - j + 1)) / (1 - phi)
        var_cum[h - 1] = sigma**2 * float((psi**2).sum())
    sd = np.sqrt(var_cum)
    z = np.asarray(Z)[:, None]
    return np.asarray(close[-1] * np.exp(mean_cum[None, :] + z * sd[None, :]), dtype=np.float64)


@dataclass
class Forecast:
    method: str
    params: dict[str, Any]
    quantiles: FloatArray  # len(QUANTILES) x horizon
    paths: FloatArray | None = None  # nur Bootstrap, für Szenario-Wahrscheinlichkeiten
    seed: int | None = None


def forecast(method: str, close: FloatArray, horizon: int = HORIZON, params: dict[str, Any] | None = None,
             seed: int = 0) -> Forecast:
    p = dict(params or DEFAULT_PARAMS[method])
    if len(close) < MIN_BARS:
        raise ValueError(f"mindestens {MIN_BARS} Kerzen nötig")
    if method == PRIMARY:
        paths = simulate_bootstrap(close, horizon, p, seed)
        return Forecast(method, {**p, "seed": seed}, quantiles_from_paths(paths), paths, seed)
    if method == COMPARISON:
        return Forecast(method, p, arima_quantiles(close, horizon, p))
    raise ValueError(f"Unbekannte Methode {method}")


# --- Beispielpfade ---------------------------------------------------------------------------------------------

# Aus den simulierten Pfaden werden die gezeigt, deren Endwert an diesen Perzentilen aller Endwerte liegt. So decken
# die Beispiele die Breite der Verteilung ab, statt nur ähnliche Verläufe zu zeigen; keiner ist wahrscheinlicher.
EXAMPLE_PERCENTILES: tuple[int, ...] = (10, 30, 50, 70, 90)


def example_path_indices(paths: FloatArray, percentiles: Sequence[int] = EXAMPLE_PERCENTILES) -> list[tuple[int, int]]:
    """(Perzentil, Pfadindex) je Perzentil: der Pfad, dessen Endwert an dieser Stelle der sortierten Endwerte liegt."""
    n = paths.shape[0]
    order = np.argsort(paths[:, -1], kind="stable")
    return [(p, int(order[min(n - 1, round(p / 100 * (n - 1)))])) for p in percentiles]


def example_path_rows(paths: FloatArray, ts: Sequence[datetime], digits: int = 4) -> list[dict[str, Any]]:
    return [{"percentile": p,
             "steps": [{"step": i + 1, "ts": ts[i].isoformat(), "close": round(float(paths[k, i]), digits)}
                       for i in range(paths.shape[1])]}
            for p, k in example_path_indices(paths)]


# --- Muster-Szenarien -------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class FirstPassage:
    upper_first: float
    lower_first: float
    neither: float


def first_passage(paths: FloatArray, upper: float, lower: float) -> FirstPassage:
    """Anteil der Pfade, deren Schlusskurs zuerst >= upper bzw. <= lower liegt (oder keins von beiden im
    Horizont). Die Niveaus bleiben über den Horizont konstant."""
    horizon = paths.shape[1]
    hit_up = paths >= upper
    hit_dn = paths <= lower
    first_up = np.where(hit_up.any(axis=1), hit_up.argmax(axis=1), horizon)
    first_dn = np.where(hit_dn.any(axis=1), hit_dn.argmax(axis=1), horizon)
    total = len(paths)
    up = float(((first_up < first_dn)).sum()) / total
    dn = float(((first_dn < first_up)).sum()) / total
    return FirstPassage(up, dn, 1.0 - up - dn)


# --- Backtest ---------------------------------------------------------------------------------------------------


def _pinball(q: FloatArray, y: float) -> float:
    taus = np.asarray(QUANTILES)
    diff = y - q
    return float(np.mean(np.maximum(taus * diff, (taus - 1) * diff)))


def norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def diebold_mariano(d: FloatArray, lag: int) -> float | None:
    """Einseitiger p-Wert für H1: mittlere Verlustdifferenz d = model - naive < 0. Newey-West-Varianz mit `lag`
    (überlappende Horizonte). None, wenn die Varianz nicht positiv ist."""
    n = len(d)
    if n < 2:
        return None
    dc = d - d.mean()
    var = float((dc * dc).sum() / n)
    for k in range(1, min(lag, n - 1) + 1):
        var += 2 * (1 - k / (lag + 1)) * float((dc[k:] * dc[:-k]).sum() / n)
    if var <= 0:
        return None
    return norm_cdf(float(d.mean()) / math.sqrt(var / n))


@dataclass
class HorizonResult:
    horizon_bars: int
    sample_size: int
    coverage: dict[float, float]
    mae_model: float
    mae_naive: float
    pinball_model: float
    pinball_naive: float
    skill: float | None
    dm_p_value: float | None
    better_than_naive: bool | None


@dataclass
class BacktestResult:
    method: str
    params: dict[str, Any]
    origins: list[int] = field(default_factory=list)
    horizons: list[HorizonResult] = field(default_factory=list)

    @property
    def sample_size(self) -> int:
        return len(self.origins)

    def at(self, h: int) -> HorizonResult | None:
        return next((r for r in self.horizons if r.horizon_bars == h), None)


def backtest_origins(n: int, params: dict[str, Any]) -> list[int]:
    """Ursprünge (Index der letzten bekannten Kerze), neueste zuerst gewählt, dann aufsteigend sortiert."""
    max_h = max(params["horizons"])
    first, last = int(params["min_train_bars"]) - 1, n - 1 - max_h
    if last < first:
        return []
    origins = list(range(last, first - 1, -int(params["step_bars"])))[: int(params["max_origins"])]
    return sorted(origins)


def rolling_backtest(method: str, close: FloatArray, params: dict[str, Any] | None = None,
                     bt: dict[str, Any] | None = None, seed_fn: Callable[[int], int] | None = None) -> BacktestResult:
    """Rollierender Ursprung ohne Vorgriff: je Ursprung o wird nur close[:o+1] verwendet und mit close[o+h]
    verglichen. Fehler in Prozent des Kurses am Ursprung."""
    p = dict(params or DEFAULT_PARAMS[method])
    b = {**BACKTEST_PARAMS, **(bt or {})}
    if method == PRIMARY:
        p["paths"] = int(b["paths"])
    horizons: list[int] = list(b["horizons"])
    max_h = max(horizons)
    origins = backtest_origins(len(close), b)
    result = BacktestResult(method, {**p, "backtest": b})
    if not origins:
        return result
    result.origins = origins
    rows: dict[int, list[tuple[FloatArray, float, float]]] = {h: [] for h in horizons}
    for o in origins:
        train = close[: o + 1]
        seed = seed_fn(o) if seed_fn else o
        fc = forecast(method, train, max_h, p, seed=seed)
        for h in horizons:
            rows[h].append((fc.quantiles[:, h - 1], float(close[o + h]), float(close[o])))
    lag_base = int(b["step_bars"])
    for h in horizons:
        cov = {lvl: 0.0 for lvl in BAND_IDX}
        err_m: list[float] = []
        err_n: list[float] = []
        pin_m: list[float] = []
        pin_n: list[float] = []
        for q, y, c0 in rows[h]:
            for lvl, (lo, hi) in BAND_IDX.items():
                cov[lvl] += float(q[lo] <= y <= q[hi])
            err_m.append(abs(q[3] - y) / c0 * 100)
            err_n.append(abs(c0 - y) / c0 * 100)
            pin_m.append(_pinball(q, y) / c0 * 100)
            pin_n.append(_pinball(np.full(len(QUANTILES), c0), y) / c0 * 100)
        n = len(rows[h])
        em, en = np.asarray(err_m), np.asarray(err_n)
        mae_m, mae_n = float(em.mean()), float(en.mean())
        skill = 1 - mae_m / mae_n if mae_n > 0 else None
        lag = max(0, -(-h // lag_base) - 1)
        p_val = diebold_mariano(em - en, lag)
        better: bool | None
        if n < int(b["min_sample"]):
            better = None
        else:
            better = bool(mae_m < mae_n and p_val is not None and p_val < float(b["alpha"]))
        result.horizons.append(HorizonResult(
            h, n, {lvl: c / n for lvl, c in cov.items()}, mae_m, mae_n, float(np.mean(pin_m)),
            float(np.mean(pin_n)), skill, p_val, better))
    return result


def quantile_rows(q: FloatArray, ts: Sequence[datetime], digits: int = 4) -> list[dict[str, Any]]:
    return [{"step": i + 1, "ts": ts[i].isoformat(),
             "quantiles": {k: round(float(q[j, i]), digits) for j, k in enumerate(QKEYS)}}
            for i in range(q.shape[1])]
