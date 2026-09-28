"""Grundregel 1: keine Empfehlungssprache. Diese Liste wird vom CI-Test und (später) zur
Laufzeit für KI-Texte verwendet. Sie ist die einzige Stelle im Code, an der die Wörter stehen."""
import re

DISCLAIMER = (
    "Dieses Dashboard stellt keine Anlageberatung dar. Alle Analysen sind automatisiert, "
    "können fehlerhaft sein und dienen ausschließlich der Information."
)

FORBIDDEN_TERMS = [
    "kaufen", "verkaufen", "kaufsignal", "verkaufssignal", "kaufempfehlung", "verkaufsempfehlung",
    "strong buy", "strong sell", "kursziel", "outperform", "underperform", "übergewichten",
    "untergewichten", "buy", "sell",
]

_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in FORBIDDEN_TERMS) + r")\b", re.IGNORECASE
)


def find_forbidden(text: str) -> list[str]:
    return sorted({m.group(1).lower() for m in _PATTERN.finditer(text)})
