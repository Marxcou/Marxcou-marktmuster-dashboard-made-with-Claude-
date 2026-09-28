"""Grundregel-Check (CI): keine Empfehlungssprache in Backend-Code und Frontend-Texten."""
from pathlib import Path

from app.grundregeln import find_forbidden

ROOT = Path(__file__).resolve().parents[2]
SKIP = {"grundregeln.py", "forbidden.ts"}
SUFFIXES = {".py", ".ts", ".tsx", ".html", ".md"}


def _files():
    for base in (ROOT / "backend" / "app", ROOT / "frontend" / "src", ROOT / "frontend" / "index.html"):
        paths = [base] if base.is_file() else base.rglob("*")
        for p in paths:
            if p.is_file() and p.suffix in SUFFIXES and p.name not in SKIP and "node_modules" not in p.parts:
                yield p


def test_no_recommendation_language():
    hits = {str(p.relative_to(ROOT)): find_forbidden(p.read_text()) for p in _files()}
    assert {k: v for k, v in hits.items() if v} == {}


def test_filter_detects_terms():
    assert find_forbidden("Wir empfehlen: Strong Buy, Kursziel 200") == ["kursziel", "strong buy"]
    assert find_forbidden("Historisch folgte in 62 % der Fälle ein Anstieg") == []
