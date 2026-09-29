"""Regressionstests der Mustererkennung: feste Kerzen-Fixtures (CSV) laufen durch die Engine, und das Ergebnis
(Muster, Zeitraum, Status, Kriterienwerte, Konfidenz, Szenario-Niveaus, Zonen) wird mit einer Golden-Datei
verglichen. Ändert sich ein Parameter oder eine Regel, zeigt der Test die Abweichung als Diff.

Absichtliche Änderung übernehmen:  UPDATE_GOLDEN=1 pytest tests/regression   (danach den Diff der Golden-Datei
im PR prüfen; bei geänderten Regeln außerdem ALGO_VERSION in app/analysis/params.py erhöhen)."""
import csv
import difflib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from app.analysis.engine import detect
from app.analysis.params import ALGO_VERSION, default_params, params_hash
from app.analysis.series import Bars

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures"
GOLDEN = HERE / "golden" / "patterns.json"
NAMES = sorted(p.stem for p in FIXTURES.glob("*.csv"))
NEGATIVE = {"seitwaerts_flach", "trend_steigend"}


def load(name: str) -> Bars:
    with (FIXTURES / f"{name}.csv").open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    return Bars.from_lists(
        [datetime.fromisoformat(r["ts_utc"]) for r in rows],
        [float(r["open"]) for r in rows], [float(r["high"]) for r in rows],
        [float(r["low"]) for r in rows], [float(r["close"]) for r in rows], [float(r["volume"]) for r in rows])


def r4(x: Any) -> Any:
    return round(float(x), 4) if isinstance(x, float) else x


def snapshot(name: str) -> dict[str, Any]:
    bars = load(name)
    res = detect(bars, "1d")
    dets = []
    for d in sorted(res.detections, key=lambda d: (d.start_idx, d.end_idx, d.pattern_type)):
        dets.append({
            "typ": d.pattern_type, "richtung": d.direction, "start": d.start_idx, "ende": d.end_idx,
            "gebildet": d.formed_idx, "status": d.status, "bestaetigt_bei": d.confirmed_idx,
            "ungueltig_bei": d.invalidated_idx, "bestaetigungsniveau": r4(d.confirmation_level),
            "ungueltigkeitsniveau": r4(d.invalidation_level), "konfidenz": r4(d.confidence),
            "konfidenz_aufschluesselung": [{k: r4(v) for k, v in b.items()} for b in d.breakdown],
            "kriterien": [{"key": c.key, "wert": r4(c.actual), "erfuellt": c.passed, "teilwert": r4(c.sub_score),
                           "gewicht": r4(c.weight)} for c in d.criteria],
            "schluesselpunkte": [{"rolle": k.role, "idx": k.idx, "kurs": r4(k.price)} for k in d.key_points],
            "szenarien": [{"art": s.kind, "niveau": r4(s.trigger_level)} for s in d.scenarios],
        })
    zones = [{"art": z.kind, "unten": r4(z.lower), "oben": r4(z.upper), "beruehrungen": len(z.touches),
              "konfidenz": r4(z.confidence)} for z in res.zones]
    return {"kerzen": len(bars), "erkennungen": dets, "zonen": zones}


def full_snapshot() -> dict[str, Any]:
    return {"algo_version": ALGO_VERSION, "params_hash": params_hash(default_params()),
            "fixtures": {n: snapshot(n) for n in NAMES}}


def render(obj: Any) -> str:
    return json.dumps(obj, indent=1, ensure_ascii=False, sort_keys=True) + "\n"


def test_fixtures_are_present() -> None:
    assert len(NAMES) >= 15


def test_golden_matches_current_engine() -> None:
    current = render(full_snapshot())
    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN.write_text(current, encoding="utf-8")
        pytest.skip("Golden-Datei neu geschrieben (UPDATE_GOLDEN=1); Diff im PR prüfen.")
    assert GOLDEN.exists(), "Golden-Datei fehlt. Erzeugen mit: UPDATE_GOLDEN=1 pytest tests/regression"
    expected = GOLDEN.read_text(encoding="utf-8")
    if current != expected:
        diff = "".join(list(difflib.unified_diff(expected.splitlines(True), current.splitlines(True),
                                                 "golden/patterns.json", "aktuell", n=2))[:400])
        pytest.fail("Die Mustererkennung liefert andere Ergebnisse als die Golden-Datei. Ist die Änderung gewollt: "
                    "UPDATE_GOLDEN=1 pytest tests/regression und den Diff prüfen.\n" + diff)


@pytest.mark.parametrize("name", sorted(NEGATIVE))
def test_negative_fixtures_detect_no_pattern(name: str) -> None:
    assert detect(load(name), "1d").detections == []


@pytest.mark.parametrize("name", NAMES)
def test_detection_is_deterministic(name: str) -> None:
    assert render(snapshot(name)) == render(snapshot(name))


@pytest.mark.parametrize("name", NAMES)
def test_every_detection_meets_explanation_duty(name: str) -> None:
    """Grundregel 3 auf Fixture-Ebene: Kriterien mit Werten, Konfidenz-Aufschlüsselung, zwei Szenario-Niveaus."""
    for d in detect(load(name), "1d").detections:
        assert d.criteria and all(c.actual_text for c in d.criteria)
        assert d.breakdown and 0.0 <= d.confidence <= 1.0
        assert len(d.scenarios) >= 2 and d.confirmation_level > 0 and d.invalidation_level > 0
        assert d.explanation


NAMED = [n for n in NAMES if n not in NEGATIVE and not n.startswith(("zufall", "doppelboden_"))]


@pytest.mark.parametrize("name", NAMED)
def test_named_fixture_contains_its_pattern(name: str) -> None:
    """Schutz davor, die Golden-Datei blind zu übernehmen: das im Namen genannte Muster muss weiterhin vorkommen."""
    assert name in {d.pattern_type for d in detect(load(name), "1d").detections}


def test_status_fixtures() -> None:
    status = {n: {d.pattern_type: d.status for d in detect(load(n), "1d").detections}
              for n in ("doppelboden_gescheitert", "doppelboden_in_bildung")}
    assert status["doppelboden_gescheitert"]["doppelboden"] == "ungueltig"
    assert status["doppelboden_in_bildung"]["doppelboden"] == "in_bildung"
