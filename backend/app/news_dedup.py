"""Duplikate erkennen: URL-Normalisierung plus Titelähnlichkeit (Jaccard über Wortmengen) innerhalb von 48 Stunden.
Beim Datenvolumen dieser Anwendung (einige hundert Meldungen pro Tag) genügt der exakte Jaccard-Vergleich; MinHash
wäre nur eine Beschleunigung ohne anderes Ergebnis."""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

CLUSTER_WINDOW_HOURS = 48
JACCARD_THRESHOLD = 0.7
MIN_TOKENS = 4  # kürzere Titel gelten nur bei identischer Wortmenge als Duplikat

_TRACKING = re.compile(r"^(utm_.*|fbclid|gclid|mc_.*|ref|cmp|cid|src|source|guccounter|taid|ocid|xtor)$", re.I)
_WORD = re.compile(r"[\wäöüß]+", re.IGNORECASE)
_SUFFIX = re.compile(r"\s+(?:[-–—|:])\s+[^-–—|:]{2,40}$")
STOPWORDS = frozenset(
    "the a an and or of to in on for at by with as is are was were be from its it that this after over "
    "der die das den dem des ein eine einen einem und oder von zu im in am an auf für mit als ist sind war wird "
    "bei nach über aus zum zur".split()
)


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query) if not _TRACKING.match(k)))
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), host, path, query, ""))


def title_tokens(title: str) -> frozenset[str]:
    t = title
    stripped = _SUFFIX.sub("", t)  # ' - Reuters', ' | CNBC' am Ende entfernen, wenn der Rest lang genug bleibt
    if len(_WORD.findall(stripped)) >= 4:
        t = stripped
    return frozenset(w.lower() for w in _WORD.findall(t) if w.lower() not in STOPWORDS and len(w) > 1)


def similar(a: frozenset[str], b: frozenset[str]) -> bool:
    if not a or not b:
        return False
    if min(len(a), len(b)) < MIN_TOKENS:
        return a == b
    return len(a & b) / len(a | b) >= JACCARD_THRESHOLD
