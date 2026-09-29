"""Muster-Backtest (3C) mit synthetischen Kursreihen, deren Ergebnis bekannt ist. Diese Zahlen landen nie in
der echten Datenbank: der Job speichert nur, was eine echte Kursquelle geliefert hat."""
import json
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from sqlalchemy import select

from app.adapters.base import AdapterMetadata, BarRecord, PriceAdapter, Timeframe
from app.adapters.http import SourceError
from app.analysis.backtest import (
    BacktestConfig,
    BaseStats,
    Case,
    InstrumentResult,
    SeenDetection,
    backtest_instrument,
    base_stats,
    jump_mask,
    slice_bars,
    summarize,
    walk_forward,
    wilson,
)
from app.analysis.catalog import PATTERN_NAMES
from app.analysis.params import default_params
from app.backtest_job import main as job_main
from app.backtest_service import load_universe, run_pattern_backtest
from app.db import SessionLocal
from app.models import BacktestRun
from tests.conftest import login
from tests.synthetic import path
from tests.test_pattern_api import run_scan, seed

CFG = BacktestConfig(warmup_bars=60, window_bars=200, step_bars=1)
# Doppelboden 30..60 (Nackenlinie ~110), danach Anstieg auf 125: Treffer
RISE = [(0, 120), (30, 100), (45, 110), (60, 100.3), (80, 125), (150, 124)]
# derselbe Doppelboden, nach der Bestätigung Rückgang auf 96: kein Treffer
FAIL = [(0, 120), (30, 100), (45, 110), (60, 100.3), (73, 111), (90, 96), (150, 97)]


def random_walk(seed_: int, n: int = 700) -> "object":
    rng = np.random.default_rng(seed_)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.018, n)))
    open_ = np.concatenate(([close[0]], close[:-1]))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.005, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.005, n)))
    ts = [datetime(2014, 1, 1, tzinfo=UTC) + timedelta(days=i) for i in range(n)]
    from app.analysis.series import Bars
    return Bars.from_lists(ts, open_.tolist(), high.tolist(), low.tolist(), close.tolist(), [1e6] * n)


# ---------- reine Rechnung ----------

def test_wilson_interval_known_values():
    lo, hi = wilson(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-4) and hi == pytest.approx(0.7634, abs=1e-4)
    lo, hi = wilson(0, 20)
    assert lo == 0.0 and hi == pytest.approx(0.1611, abs=1e-4)
    with pytest.raises(ValueError):
        wilson(0, 0)


def test_confirmed_double_bottom_then_rise_is_a_hit():
    r = backtest_instrument("X.XETR", path(RISE), "1d", None, CFG)
    db = next(d for d in r.detections if d.pattern_type == "doppelboden")
    assert db.status == "bestaetigt" and db.status_at_seen == "in_bildung"
    assert db.first_seen_idx > db.end_idx  # erst sichtbar, nachdem die Wendepunkte feststehen
    case = next(c for c in r.cases if c.pattern_type == "doppelboden")
    assert case.entry_idx == max(db.confirmed_idx or 0, db.first_seen_idx)
    assert case.hit is True and case.return_pct is not None and case.return_pct > 5


def test_confirmed_double_bottom_then_drop_is_no_hit():
    r = backtest_instrument("X.XETR", path(FAIL), "1d", None, CFG)
    case = next(c for c in r.cases if c.pattern_type == "doppelboden")
    assert case.hit is False and case.return_pct is not None and case.return_pct < 0


def test_walk_forward_has_no_lookahead():
    """Was bis zum Tag T sichtbar war, hängt nicht von späteren Kerzen ab: Lauf auf der ganzen Reihe und auf
    der bei T abgeschnittenen Reihe liefern bis T dieselben Erkennungen mit demselben Sichtbarkeitstag."""
    bars = random_walk(7)
    cfg = BacktestConfig(warmup_bars=250, window_bars=300, step_bars=5)
    full = walk_forward(bars, "1d", default_params(), cfg)
    t_cut = 249 + 5 * 60  # liegt auf dem Raster der Erkennungsläufe
    cut = walk_forward(slice_bars(bars, 0, t_cut + 1), "1d", default_params(), cfg)

    def key(d: SeenDetection) -> tuple[str, int, int, int, str]:
        return d.pattern_type, d.start_idx, d.end_idx, d.first_seen_idx, d.status_at_seen

    assert full and cut
    assert sorted(map(key, cut)) == sorted(key(d) for d in full if d.first_seen_idx <= t_cut)


def test_case_never_starts_before_the_pattern_was_visible():
    r = backtest_instrument("RW", random_walk(3), "1d", None, BacktestConfig(warmup_bars=250, step_bars=5))
    seen = {(d.pattern_type, d.confirmed_idx): d for d in r.detections if d.status == "bestaetigt"}
    assert r.cases
    for c in r.cases:
        assert any(c.entry_idx >= d.first_seen_idx and c.entry_idx >= (d.confirmed_idx or 0)
                   for (pt, _), d in seen.items() if pt == c.pattern_type)


def test_base_rate_counts_every_trading_day():
    close = 100 * 1.01 ** np.arange(100)  # jeden Tag +1 %
    cfg = BacktestConfig(horizon_bars=10, min_move_pct=5.0)
    stats = base_stats(close, jump_mask(close, 40), 0, cfg)
    assert stats["aufwärts"].days == 90 and stats["aufwärts"].rate == 1.0
    assert stats["abwärts"].rate == 0.0
    assert stats["aufwärts"].mean_return_pct == pytest.approx((1.01 ** 10 - 1) * 100)


def test_windows_with_price_jump_are_excluded():
    close = np.concatenate((np.full(50, 100.0), np.full(50, 40.0)))  # z. B. nicht bereinigter Split
    jumps = jump_mask(close, 40)
    assert jumps.sum() == 1
    stats = base_stats(close, jumps, 0, BacktestConfig(horizon_bars=10))
    assert stats["abwärts"].hits == 0 and stats["aufwärts"].days == 90 - 10


def _result(cases: list[Case], base: float) -> InstrumentResult:
    r = InstrumentResult("X.XETR", 1000, 0, cases=cases)
    r.base = {"aufwärts": BaseStats(1000, int(base * 1000), 0.0), "abwärts": BaseStats(1000, 0, 0.0)}
    return r


def _cases(hits: int, n: int) -> list[Case]:
    return [Case("doppelboden", "aufwärts", i, i < hits, 1.0) for i in range(n)]


def test_summary_says_openly_when_not_better_than_chance():
    s = summarize("doppelboden", [_result(_cases(52, 100), 0.5)])
    assert s.sample_size == 100 and s.hit_rate == 0.52
    assert s.ci_low is not None and s.base_rate is not None and s.ci_low <= s.base_rate
    assert s.verdict_text is not None and "überdeckt die Basisrate" in s.verdict_text

    above = summarize("doppelboden", [_result(_cases(80, 100), 0.5)])
    assert above.ci_low is not None and above.ci_low > 0.5 and "schließt sie aus" in (above.verdict_text or "")
    below = summarize("doppelboden", [_result(_cases(20, 100), 0.5)])
    assert "unter der Basisrate" in (below.verdict_text or "")


def test_summary_without_cases_estimates_nothing():
    s = summarize("keil_fallend", [_result(_cases(5, 10), 0.5)])
    assert s.sample_size == 0 and s.hit_rate is None and s.ci_low is None and s.base_rate is None
    assert "keine Trefferquote geschätzt" in s.note


def test_open_and_excluded_cases_do_not_count():
    cases = _cases(1, 2) + [Case("doppelboden", "aufwärts", 5, None, None),
                            Case("doppelboden", "aufwärts", 6, None, None, excluded=True)]
    s = summarize("doppelboden", [_result(cases, 0.5)])
    assert s.sample_size == 2 and s.cases_open == 1 and s.cases_excluded == 1


# ---------- Job mit Datenbank ----------

class FakeStooq(PriceAdapter):
    """Liefert vorgegebene Kerzen wie ein Kursadapter (im Test statt des Netzwerks)."""
    key = "stooq"
    supported_exchanges = ("XETR", "XNAS", "XNYS")

    def __init__(self, series: dict[str, list[tuple[datetime, float]]], fail: set[str] | None = None) -> None:
        self.series, self.fail, self.calls = series, fail or set(), 0

    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(key="stooq", name="Stooq", kind="price", description="", homepage="https://stooq.com",
                               terms_url="https://stooq.com/", update_interval="täglich", delay_text="Handelsende",
                               requires_key=True)

    def is_configured(self) -> bool:
        return True

    def health(self):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def fetch_bars(self, symbol: str, exchange: str, timeframe: Timeframe, start: datetime,
                   end: datetime) -> list[BarRecord]:
        self.calls += 1
        if symbol in self.fail:
            raise SourceError("Limit erreicht")
        now = datetime(2026, 9, 29, 12, tzinfo=UTC)
        return [BarRecord(symbol, exchange, "1d", ts, c, c * 1.002, c * 0.998, c, 1e6, "stooq", now)
                for ts, c in self.series.get(symbol, [])]


def _series(anchors: list[tuple[int, float]], end: datetime) -> list[tuple[datetime, float]]:
    b = path(anchors)
    n = len(b)
    return [(end - timedelta(days=n - i), float(b.close[i])) for i in range(n)]


NOW = datetime(2026, 9, 29, 12, tzinfo=UTC)
START = datetime(2020, 1, 1, tzinfo=UTC)


def test_job_writes_one_run_per_pattern_with_source_and_api_shows_it(client, tmp_path):
    adapter = FakeStooq({"SAP": _series(RISE, NOW), "SIE": _series(FAIL, NOW), "EMPTY": []}, fail={"BAD"})
    universe = [("SAP", "XETR"), ("SIE", "XETR"), ("EMPTY", "XETR"), ("BAD", "XETR")]
    cfg = BacktestConfig(warmup_bars=60, window_bars=200, step_bars=1, horizon_bars=20)
    with SessionLocal() as db:
        summaries, data = run_pattern_backtest(db, adapter, universe, "Testauswahl", START, cfg, 1, tmp_path, now=NOW)
    assert [s.key for s in data.series] == ["SAP.XETR", "SIE.XETR"]
    assert set(data.missing) == {"EMPTY.XETR", "BAD.XETR"} and "Limit" in data.missing["BAD.XETR"]
    with SessionLocal() as db:
        runs = db.scalars(select(BacktestRun)).all()
        assert sorted(r.subject for r in runs) == sorted(PATTERN_NAMES)
        dbl = next(r for r in runs if r.subject == "doppelboden")
        assert dbl.kind == "pattern" and dbl.timeframe == "1d" and dbl.algo_version == "1.0.0"
        assert dbl.sample_size == 2 and dbl.hit_rate == 0.5
        assert dbl.params["horizon_bars"] == 20 and dbl.params["min_move_pct"] == 5.0
        assert "Stooq" in dbl.universe and "2 Werte mit Daten, 2 ohne" in dbl.universe
        assert dbl.metrics["source"]["key"] == "stooq" and dbl.metrics["symbols_missing"]["BAD.XETR"]
        assert dbl.metrics["survivorship_note"] and dbl.metrics["scenarios"]["bestaetigung"]["sample_size"] == 2
        empty = next(r for r in runs if r.subject == "wimpel_abwaerts")
        assert empty.sample_size == 0 and empty.hit_rate is None and empty.base_rate is None

    # Die Musteransicht zeigt den Lauf (Lookup: neuester Lauf je Mustertyp, Zeitraster, Algorithmus-Version)
    iid, _ = seed()
    run_scan(iid)
    login(client)
    det = next(d for d in client.get(f"/api/instruments/{iid}/patterns").json()["detections"]
               if d["pattern_type"] == "doppelboden")
    bt = det["backtest"]
    assert bt["status"] == "berechnet" and bt["sample_size"] == 2 and bt["source"]["name"] == "Stooq"
    assert bt["method"] and bt["mean_return_pct"] is not None
    assert det["scenarios"][0]["historical"]["sample_size"] == 2

    # zweiter Lauf nutzt den Zwischenspeicher statt der Quelle
    calls = adapter.calls
    with SessionLocal() as db:
        load_universe(adapter, universe[:2], START, NOW, tmp_path, timedelta(days=7), 80)
    assert adapter.calls == calls
    cached = json.loads((tmp_path / "stooq" / "SAP.XETR.json").read_text())
    assert cached["source_key"] == "stooq" and cached["fetched_at"].startswith("2026-09-29")


def test_job_without_data_stores_nothing(client, tmp_path):
    adapter = FakeStooq({}, fail={"SAP"})
    with SessionLocal() as db, pytest.raises(ValueError, match="kein Ergebnis gespeichert"):
        run_pattern_backtest(db, adapter, [("SAP", "XETR"), ("SIE", "XETR")], "Test", START, CFG, 1, tmp_path,
                             now=NOW)
    with SessionLocal() as db:
        assert db.scalars(select(BacktestRun)).all() == []


def test_todays_running_bar_is_not_used(tmp_path):
    series = _series(RISE, NOW + timedelta(days=1))  # letzte Kerze = heute (läuft noch)
    data = load_universe(FakeStooq({"SAP": series}), [("SAP", "XETR")], START, NOW, None, timedelta(days=7), 60)
    assert data.series[0].bars.ts[-1].date() < NOW.date()


def test_job_refuses_without_stooq_key(monkeypatch, capsys):
    monkeypatch.setattr("app.backtest_job.StooqAdapter.is_configured", lambda self: False)
    assert job_main(["--dry-run"]) == 2
    assert "STOOQ_API_KEY" in capsys.readouterr().err


def test_not_better_than_random_also_when_clearly_below_base_rate(client):
    iid, _ = seed()
    run_scan(iid)
    with SessionLocal() as db:
        db.add(BacktestRun(kind="pattern", subject="doppelboden", timeframe="1d", algo_version="1.0.0",
                           params={"horizon_bars": 20, "min_move_pct": 5.0}, universe="Test", sample_size=100,
                           hit_rate=0.2, ci_low=0.13, ci_high=0.29, base_rate=0.5, metrics={}))
        db.commit()
    login(client)
    det = next(d for d in client.get(f"/api/instruments/{iid}/patterns").json()["detections"]
               if d["pattern_type"] == "doppelboden")
    assert det["backtest"]["not_better_than_random"] is True
