"""Muster-Backtest (Workstream 3C): reines numpy, ohne I/O, deterministisch.

Ablauf je Aktie, ohne Blick in die Zukunft (walk-forward):
1. Für t = Start, Start + Schritt, ... läuft die Mustererkennung nur auf den Kerzen bis einschließlich t
   (höchstens `window_bars` Kerzen). Jede Erkennung wird mit dem ersten t gemerkt, an dem sie sichtbar war.
2. Der Status (bestätigt/ungültig) wird mit denselben Regeln wie in der Engine (`evaluate_status`) auf den
   Kerzen nach dem Musterende ausgewertet.
3. Ein Fall ist eine bestätigte Erkennung. Ausgangspunkt ist der Schlusskurs an der späteren der beiden Kerzen
   "Bestätigung" und "erstmals sichtbar". Treffer: ein Schlusskurs innerhalb der nächsten `horizon_bars`
   Kerzen liegt mindestens `min_move_pct` % in der Richtung des Musters.
4. Basisrate: derselbe Test für jeden Handelstag derselben Aktie im ausgewerteten Zeitraum, in derselben
   Richtung. Sie wird wie die Fälle gewichtet (je Fall die Basisrate seiner Aktie und Richtung).

Kerzenfolgen mit einem Tagessprung über `max_daily_jump_pct` % (z. B. nicht bereinigte Aktiensplits) werden
nicht ausgewertet und als ausgeschlossen gezählt. Es wird nichts geschätzt: ohne Fälle bleibt die Quote leer."""
import copy
import dataclasses
import math
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from app.analysis import fmt
from app.analysis.engine import MIN_BARS, detect
from app.analysis.params import Params, default_params
from app.analysis.patterns.common import Context, Detection, Status, evaluate_status
from app.analysis.series import Bars, FloatArray

BACKTEST_VERSION = "1.0.0"
Move = Literal["aufwärts", "abwärts"]
Z95 = 1.959963984540054

SURVIVORSHIP_NOTE = (
    "Die Aktienauswahl besteht aus heutigen Indexmitgliedern. Unternehmen, die früher im Index waren und "
    "ausgeschieden oder vom Markt verschwunden sind, fehlen (Survivorship Bias); das kann die Ergebnisse verzerren."
)
DEPENDENCE_NOTE = (
    "Fälle derselben Aktie können sich zeitlich überschneiden und sind nicht unabhängig; das 95-%-Intervall "
    "(Wilson) ist daher eher zu schmal."
)


@dataclass(frozen=True)
class BacktestConfig:
    horizon_bars: int = 20
    min_move_pct: float = 5.0
    window_bars: int = 500  # Kerzen je Erkennungslauf (breiteste Muster: 250 Kerzen plus Vorlauf)
    step_bars: int = 5  # Abstand der Erkennungsläufe; ein Fall beginnt nie vor seiner Sichtbarkeit
    warmup_bars: int = 250  # erster Erkennungslauf nach so vielen Kerzen
    max_daily_jump_pct: float = 40.0

    def as_params(self) -> dict[str, float | int]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class SeenDetection:
    """Eine Erkennung in Indizes der vollständigen Reihe."""
    pattern_type: str
    direction: str
    start_idx: int
    end_idx: int
    first_seen_idx: int
    status_at_seen: Status
    status: Status
    confirmed_idx: int | None
    breakout_direction: str | None


@dataclass(frozen=True)
class Case:
    pattern_type: str
    direction: Move
    entry_idx: int
    hit: bool | None  # None: zu wenige Kerzen danach (noch offen)
    return_pct: float | None  # Veränderung nach horizon_bars Kerzen in Musterrichtung
    excluded: bool = False  # Tagessprung im Auswertungsfenster


@dataclass(frozen=True)
class BaseStats:
    days: int
    hits: int
    return_sum_pct: float

    @property
    def rate(self) -> float | None:
        return self.hits / self.days if self.days else None

    @property
    def mean_return_pct(self) -> float | None:
        return self.return_sum_pct / self.days if self.days else None


@dataclass
class InstrumentResult:
    symbol: str
    bar_count: int
    eval_from_idx: int
    detections: list[SeenDetection] = field(default_factory=list)
    cases: list[Case] = field(default_factory=list)
    base: dict[str, BaseStats] = field(default_factory=dict)  # je Richtung
    jump_count: int = 0


def slice_bars(bars: Bars, lo: int, hi: int) -> Bars:
    return Bars(bars.ts[lo:hi], bars.open[lo:hi], bars.high[lo:hi], bars.low[lo:hi], bars.close[lo:hi],
                bars.volume[lo:hi])


def _shift(det: Detection, off: int) -> Detection:
    """Kopie mit Indizes der vollständigen Reihe und zurückgesetztem Status."""
    d = copy.copy(det)
    d.start_idx, d.end_idx, d.formed_idx = det.start_idx + off, det.end_idx + off, det.formed_idx + off
    d.deadline_idx = det.deadline_idx + off
    d.apex_idx = None if det.apex_idx is None else det.apex_idx + off
    d.confirmation = dataclasses.replace(det.confirmation, i0=det.confirmation.i0 + off, i1=det.confirmation.i1 + off)
    d.invalidation = dataclasses.replace(det.invalidation, i0=det.invalidation.i0 + off, i1=det.invalidation.i1 + off)
    d.status, d.status_reason, d.status_idx = "in_bildung", "", None
    d.confirmed_idx = d.invalidated_idx = None
    d.breakout_direction = None
    return d


def _overlaps(a: SeenDetection, start: int, end: int) -> bool:
    overlap = min(a.end_idx, end) - max(a.start_idx, start)
    shorter = max(1, min(a.end_idx - a.start_idx, end - start))
    return overlap / shorter >= 0.5


def walk_forward(bars: Bars, timeframe: str, params: Params, cfg: BacktestConfig) -> list[SeenDetection]:
    """Alle Erkennungen, die bei schrittweiser Auswertung jemals sichtbar waren, je Muster einmal (überlappt eine
    spätere Erkennung desselben Typs eine frühere um mindestens die Hälfte, gilt sie als dasselbe Muster)."""
    n = len(bars)
    first = max(cfg.warmup_bars, MIN_BARS) - 1
    if n <= first:
        return []
    ts = list(range(first, n, cfg.step_bars))
    if ts[-1] != n - 1:
        ts.append(n - 1)
    full_ctx = Context(bars, np.zeros(0), [], params, timeframe)
    seen: list[SeenDetection] = []
    by_type: dict[str, list[SeenDetection]] = {}
    for t in ts:
        lo = max(0, t + 1 - cfg.window_bars)
        for det in detect(slice_bars(bars, lo, t + 1), timeframe, params).detections:
            start, end = det.start_idx + lo, det.end_idx + lo
            prior = by_type.setdefault(det.pattern_type, [])
            if any(_overlaps(p, start, end) for p in prior):
                continue
            full = _shift(det, lo)
            evaluate_status(full_ctx, full)
            s = SeenDetection(det.pattern_type, det.direction, start, end, t, det.status, full.status,
                              full.confirmed_idx, full.breakout_direction)
            prior.append(s)
            seen.append(s)
    return sorted(seen, key=lambda s: (s.first_seen_idx, s.start_idx, s.pattern_type))


def jump_mask(close: FloatArray, max_jump_pct: float) -> np.ndarray:
    """jump[i] = True, wenn der Schlusskurs von i-1 auf i um mehr als max_jump_pct % springt."""
    out = np.zeros(len(close), dtype=bool)
    if len(close) > 1:
        out[1:] = np.abs(close[1:] / close[:-1] - 1.0) * 100.0 > max_jump_pct
    return out


def _has_jump(jumps: np.ndarray, lo: int, hi: int) -> bool:
    """Sprung zwischen den Kerzen lo..hi (Sprünge auf Kerze lo+1 bis hi)."""
    return bool(jumps[lo + 1 : hi + 1].any())


def outcome(close: FloatArray, entry: int, direction: Move, cfg: BacktestConfig) -> tuple[bool, float]:
    base = float(close[entry])
    future = close[entry + 1 : entry + cfg.horizon_bars + 1]
    x = cfg.min_move_pct / 100.0
    hit = bool((future >= base * (1 + x)).any()) if direction == "aufwärts" else bool((future <= base * (1 - x)).any())
    ret = (float(close[entry + cfg.horizon_bars]) / base - 1.0) * 100.0
    return hit, ret if direction == "aufwärts" else -ret


def cases_from(detections: list[SeenDetection], close: FloatArray, jumps: np.ndarray,
               cfg: BacktestConfig) -> list[Case]:
    n = len(close)
    out: list[Case] = []
    for d in detections:
        if d.status != "bestaetigt" or d.confirmed_idx is None:
            continue
        move = d.breakout_direction if d.direction == "offen" else d.direction
        if move not in ("aufwärts", "abwärts"):
            continue
        direction: Move = "aufwärts" if move == "aufwärts" else "abwärts"
        entry = max(d.confirmed_idx, d.first_seen_idx)
        if entry + cfg.horizon_bars > n - 1:
            out.append(Case(d.pattern_type, direction, entry, None, None))
        elif _has_jump(jumps, d.start_idx, entry + cfg.horizon_bars):
            out.append(Case(d.pattern_type, direction, entry, None, None, excluded=True))
        else:
            hit, ret = outcome(close, entry, direction, cfg)
            out.append(Case(d.pattern_type, direction, entry, hit, ret))
    return out


def base_stats(close: FloatArray, jumps: np.ndarray, from_idx: int, cfg: BacktestConfig) -> dict[str, BaseStats]:
    """Derselbe Treffertest für jeden Handelstag from_idx .. n-1-horizon (ohne Tage mit Sprung im Fenster)."""
    h, n = cfg.horizon_bars, len(close)
    last = n - 1 - h
    if last < from_idx:
        return {"aufwärts": BaseStats(0, 0, 0.0), "abwärts": BaseStats(0, 0, 0.0)}
    starts = np.arange(from_idx, last + 1)
    win = np.lib.stride_tricks.sliding_window_view(close, h + 1)[starts]  # Zeile: Kerze t .. t+h
    jwin = np.lib.stride_tricks.sliding_window_view(jumps, h + 1)[starts][:, 1:]
    ok = ~jwin.any(axis=1)
    win = win[ok]
    x = cfg.min_move_pct / 100.0
    base = win[:, 0]
    fut = win[:, 1:]
    ret = (win[:, -1] / base - 1.0) * 100.0
    days = int(ok.sum())
    return {
        "aufwärts": BaseStats(days, int((fut.max(axis=1) >= base * (1 + x)).sum()), float(ret.sum())),
        "abwärts": BaseStats(days, int((fut.min(axis=1) <= base * (1 - x)).sum()), float(-ret.sum())),
    }


def backtest_instrument(symbol: str, bars: Bars, timeframe: str = "1d", params: Params | None = None,
                        cfg: BacktestConfig | None = None) -> InstrumentResult:
    params = params or default_params()
    cfg = cfg or BacktestConfig()
    close = bars.close
    jumps = jump_mask(close, cfg.max_daily_jump_pct)
    eval_from = max(cfg.warmup_bars, MIN_BARS) - 1
    res = InstrumentResult(symbol, len(bars), eval_from, jump_count=int(jumps.sum()))
    res.detections = walk_forward(bars, timeframe, params, cfg)
    res.cases = cases_from(res.detections, close, jumps, cfg)
    res.base = base_stats(close, jumps, eval_from, cfg)
    return res


# ---------- Zusammenfassung je Mustertyp ----------

def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """95-%-Konfidenzintervall nach Wilson für eine Trefferquote k/n."""
    if n == 0:
        raise ValueError("n muss größer als 0 sein")
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def share(x: float) -> str:
    return fmt.pct(x * 100, 1)


@dataclass
class PatternSummary:
    pattern_type: str
    sample_size: int
    hits: int
    hit_rate: float | None
    ci_low: float | None
    ci_high: float | None
    base_rate: float | None
    mean_return_pct: float | None
    median_return_pct: float | None
    base_mean_return_pct: float | None
    cases_open: int
    cases_excluded: int
    detections_seen: int
    symbols_with_cases: int
    scenarios: dict[str, dict[str, float | int | str | None]]
    verdict_text: str | None
    note: str


def _verdict(hit: float, lo: float, hi: float, base: float) -> str:
    rng = f"95-%-Intervall {share(lo)} bis {share(hi)}"
    if lo > base:
        return f"Die Trefferquote ({share(hit)}) liegt über der Basisrate ({share(base)}); das {rng} schließt sie aus."
    if hi < base:
        return (f"Die Trefferquote ({share(hit)}) liegt unter der Basisrate ({share(base)}); das {rng} liegt "
                "vollständig darunter.")
    return f"Das {rng} überdeckt die Basisrate ({share(base)})."


def _scenarios(pattern_type: str, dets: list[SeenDetection]) -> dict[str, dict[str, float | int | str | None]]:
    """Anteile unter den Erkennungen, die noch in Bildung waren, als sie erstmals sichtbar wurden, und deren
    Ausgang bis zum Datenende feststeht."""
    pool = [d for d in dets if d.status_at_seen == "in_bildung" and d.status != "in_bildung"]
    n = len(pool)

    def entry(count: int, what: str) -> dict[str, float | int | str | None]:
        if n == 0:
            return {"share": None, "sample_size": 0,
                    "text": "Im Backtest-Zeitraum gab es keine abgeschlossene Erkennung dieses Musters."}
        return {"share": round(count / n, 4), "sample_size": n,
                "text": f"In {share(count / n)} von {n} in Echtzeit erkannten Fällen {what}."}

    confirmed = [d for d in pool if d.status == "bestaetigt"]
    invalid = n - len(confirmed)
    if pattern_type == "dreieck_symmetrisch":
        up = sum(1 for d in confirmed if d.breakout_direction == "aufwärts")
        return {"ausbruch_oben": entry(up, "folgte ein Ausbruch nach oben"),
                "ausbruch_unten": entry(len(confirmed) - up, "folgte ein Ausbruch nach unten")}
    return {"bestaetigung": entry(len(confirmed), "wurde das Muster bestätigt"),
            "scheitern": entry(invalid, "wurde das Muster ungültig, bevor es bestätigt wurde")}


def summarize(pattern_type: str, results: list[InstrumentResult]) -> PatternSummary:
    evaluated: list[tuple[Case, BaseStats]] = []
    open_, excluded, seen = 0, 0, 0
    dets: list[SeenDetection] = []
    symbols: set[str] = set()
    for r in results:
        mine = [d for d in r.detections if d.pattern_type == pattern_type]
        dets += mine
        seen += len(mine)
        for c in r.cases:
            if c.pattern_type != pattern_type:
                continue
            if c.excluded:
                excluded += 1
            elif c.hit is None:
                open_ += 1
            else:
                evaluated.append((c, r.base[c.direction]))
                symbols.add(r.symbol)
    n = len(evaluated)
    k = sum(1 for c, _ in evaluated if c.hit)
    out = PatternSummary(
        pattern_type=pattern_type, sample_size=n, hits=k, hit_rate=None, ci_low=None, ci_high=None, base_rate=None,
        mean_return_pct=None, median_return_pct=None, base_mean_return_pct=None, cases_open=open_,
        cases_excluded=excluded, detections_seen=seen, symbols_with_cases=len(symbols),
        scenarios=_scenarios(pattern_type, dets), verdict_text=None,
        note="Im Backtest-Zeitraum trat kein auswertbarer bestätigter Fall dieses Musters auf. "
             "Es wird keine Trefferquote geschätzt.")
    if n == 0:
        return out
    hit_rate = k / n
    lo, hi = wilson(k, n)
    base_rates = [b.rate for _, b in evaluated if b.rate is not None]
    base_rets = [b.mean_return_pct for _, b in evaluated if b.mean_return_pct is not None]
    base = float(np.mean(base_rates)) if base_rates else None
    rets = [c.return_pct for c, _ in evaluated if c.return_pct is not None]
    out.hit_rate, out.ci_low, out.ci_high = round(hit_rate, 4), round(lo, 4), round(hi, 4)
    out.base_rate = None if base is None else round(base, 4)
    out.mean_return_pct = round(float(np.mean(rets)), 3)
    out.median_return_pct = round(float(np.median(rets)), 3)
    out.base_mean_return_pct = round(float(np.mean(base_rets)), 3) if base_rets else None
    out.verdict_text = None if base is None else _verdict(hit_rate, lo, hi, base)
    out.note = DEPENDENCE_NOTE
    return out
