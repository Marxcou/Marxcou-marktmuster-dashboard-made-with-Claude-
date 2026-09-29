"""Einstiegspunkt der Mustererkennung: Kerzen + Parameter -> Erkennungen und Zonen (deterministisch)."""
from dataclasses import dataclass

from app.analysis.params import Params, default_params
from app.analysis.patterns.common import Context, Detection, dedupe
from app.analysis.patterns.double import find_double
from app.analysis.patterns.flags import find_flags
from app.analysis.patterns.head_shoulders import find_head_shoulders
from app.analysis.patterns.triangles import find_triangles
from app.analysis.pivots import Pivot, zigzag
from app.analysis.series import Bars, atr
from app.analysis.zones import Zone, find_zones

MIN_BARS = 60


@dataclass
class EngineResult:
    detections: list[Detection]
    zones: list[Zone]
    pivots: list[Pivot]


def build_context(bars: Bars, timeframe: str, params: Params | None = None) -> Context:
    params = params or default_params()
    pp = params["pivots"]
    a = atr(bars, int(pp["atr_periode"]))
    pivots = zigzag(bars, a, pp["atr_faktor"], pp["min_bewegung_pct"])
    return Context(bars, a, pivots, params, timeframe)


def detect(bars: Bars, timeframe: str, params: Params | None = None) -> EngineResult:
    if len(bars) < MIN_BARS:
        return EngineResult([], [], [])
    ctx = build_context(bars, timeframe, params)
    found = find_double(ctx) + find_head_shoulders(ctx) + find_triangles(ctx) + find_flags(ctx)
    return EngineResult(dedupe(found), find_zones(ctx), ctx.pivots)
