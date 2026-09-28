"""Hilfen für News-Adapter: kurzer Auszug (nie Volltext), Zeitparser, Symbol-Konventionen."""
import html
import re
from datetime import UTC, datetime

EXCERPT_MAX = 300
_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def clean_excerpt(text: str | None, max_len: int = EXCERPT_MAX) -> str:
    """Entfernt HTML, normalisiert Leerraum und kürzt an einer Wortgrenze auf höchstens max_len Zeichen."""
    if not text:
        return ""
    t = _WS.sub(" ", html.unescape(_TAGS.sub(" ", text))).strip()
    if len(t) <= max_len:
        return t
    cut = t[: max_len - 1].rsplit(" ", 1)[0].rstrip(" ,;:.-")
    return cut + "…"


def clean_title(text: str | None) -> str:
    return _WS.sub(" ", html.unescape(_TAGS.sub(" ", text or ""))).strip()[:500]


def utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def company_search_name(name: str) -> str:
    """Firmenname ohne Rechtsform ('Apple Inc.' -> 'Apple'), für Namenssuche und Namensabgleich."""
    n = re.sub(r"[.,]", " ", name)
    n = re.sub(
        r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|llc|ag|se|kgaa|gmbh|nv|sa|holdings?|group|"
        r"class [a-c]|common stock|ordinary shares?|adr)\b",
        " ", n, flags=re.IGNORECASE,
    )
    return _WS.sub(" ", n).strip()


def xetra_symbol(symbol: str) -> str:
    return f"{symbol}.DE"
