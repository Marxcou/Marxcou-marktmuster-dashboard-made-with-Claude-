"""Stimmung per Wortliste (regelbasiert, deterministisch, ohne Modell und ohne Kosten). Dieses Verfahren ist immer
verfügbar und der Ausweichweg, wenn kein Claude-Schlüssel gesetzt oder das Monatslimit erreicht ist.

Vorgehen: Überschrift und Auszug werden nach positiven und negativen Formulierungen durchsucht. Steht ein
Verneinungswort ('not', 'nicht', 'kein', 'ohne' ...) höchstens zwei Wörter davor, kehrt sich die Wertung um.
Score = (positiv - negativ) / (positiv + negativ); ab +0,25 'positiv', ab -0,25 'negativ', sonst 'neutral'.
Die Wortlisten sind eine eigene, bewusst kleine Auswahl (kein Fremdlexikon) und in LEXICON_VERSION versioniert.
Ein '*' am Ende bedeutet: beliebige Wortendung (Wortstamm)."""
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from app.adapters.base import AdapterMetadata, Health, SourceAdapter

LEXICON_VERSION = "de-en-1"
MODEL_NAME = "Finanz-Lexikon (regelbasiert)"

POS_EN = [
    "record profit*", "record revenue", "record high*", "beats estimates", "beat estimates", "beats expectations",
    "raises guidance", "raised guidance", "raises forecast", "raised its forecast", "upgraded", "upgrade*",
    "surge*", "soar*", "jump*", "rall*", "gain*", "rise*", "rose", "climb*", "strong*", "growth", "grow*",
    "profit*", "profitable", "approval", "approved", "wins", "won", "breakthrough", "expands", "expansion",
    "dividend increase", "raises dividend", "share repurchase", "buyback*", "outlook improved", "recover*",
    "boost*", "optimis*", "successful", "success",
]
NEG_EN = [
    "misses estimates", "missed estimates", "misses expectations", "cuts guidance", "cut guidance", "lowers forecast",
    "lowered its forecast", "downgraded", "downgrade*", "plunge*", "plummet*", "tumble*", "slump*", "drop*", "fall*",
    "fell", "decline*", "weak*", "loss*", "losses", "lawsuit*", "sued", "investigation*", "probe*", "fraud*",
    "recall*", "bankruptcy", "insolvenc*", "layoff*", "job cuts", "fine", "fined", "penalt*", "warning", "warns",
    "profit warning", "shortfall", "delay*", "default*", "scandal*", "breach*", "halted", "concern*", "risk*", "crisis",
]
POS_DE = [
    "rekordgewinn*", "rekordumsatz", "rekordhoch*", "übertrifft", "übertroffen", "hebt prognose an",
    "prognose angehoben", "prognoseerhöhung", "hochgestuft", "hochstufung", "kurssprung", "kräftig*", "steigt",
    "steigen", "stieg*", "gewinn*", "wachstum", "wächst", "wachsen", "zuversicht*", "erholung", "erholt", "genehmigung",
    "genehmigt", "durchbruch", "erfolg*", "dividendenerhöhung", "aktienrückkauf", "auftragsplus", "zugewinn*",
    "verbessert*", "stark*", "rückenwind", "übernahme angebot",
]
NEG_DE = [
    "verfehlt", "verfehlen", "senkt prognose", "prognose gesenkt", "prognosesenkung", "gewinnwarnung", "herabgestuft",
    "abstufung", "kurssturz", "einbruch", "einbrüche", "bricht ein", "fällt", "fallen", "fielen", "verlust*",
    "verluste",
    "klage*", "verklagt", "ermittlung*", "betrug", "rückruf*", "insolvenz*", "stellenabbau", "entlassung*", "strafe",
    "bußgeld", "warnung", "warnt", "rückgang", "rückläufig", "schwach*", "verzögerung*", "skandal*", "krise",
    "belastet", "belastung*", "sorgen", "risiko", "risiken", "abschreibung*",
]
NEGATIONS = {"not", "no", "without", "never", "fails", "failed", "nicht", "kein", "keine", "keinen", "ohne", "nie"}
THRESHOLD = 0.25

_WORD = re.compile(r"[\wäöüßÄÖÜ]+(?:[-'][\wäöüß]+)*", re.UNICODE)


def _compile(entries: list[str]) -> list[tuple[re.Pattern[str], str]]:
    out = []
    for e in entries:
        stem = e.endswith("*")
        body = re.escape(e.rstrip("*")).replace(r"\ ", r"\s+")
        tail = r"[\wäöüß]*" if stem else r"(?![\wäöüß])"
        out.append((re.compile(r"(?<![\wäöüß])" + body + tail, re.IGNORECASE), e))
    return out


_POS = {"en": _compile(POS_EN), "de": _compile(POS_DE)}
_NEG = {"en": _compile(NEG_EN), "de": _compile(NEG_DE)}


@dataclass(frozen=True)
class SentimentResult:
    label: str
    score: float
    evidence: list[str]
    rationale: str
    method: str
    model_name: str
    model_version: str
    source_key: str


def _langs(language: str | None) -> list[str]:
    return [language] if language in ("en", "de") else ["en", "de"]


def _negated(text: str, start: int) -> int | None:
    """Startposition des Verneinungswortes, wenn eines höchstens zwei Wörter vor `start` steht."""
    before = list(_WORD.finditer(text[:start]))[-2:]
    for m in reversed(before):
        if m.group(0).lower() in NEGATIONS:
            return m.start()
    return None


def analyze(title: str, excerpt: str, language: str | None) -> SentimentResult:
    text = f"{title}. {excerpt}" if excerpt else title
    hits: list[tuple[int, int, int, bool]] = []  # (start, end, polarity, ist_wortstamm)
    for lang in _langs(language):
        for pol, table in ((1, _POS[lang]), (-1, _NEG[lang])):
            for pat, entry in table:
                for m in pat.finditer(text):
                    hits.append((m.start(), m.end(), pol, entry.endswith("*")))
    # Bei gleichem Anfang gewinnt der längste Treffer, bei Gleichstand der ausdrückliche Eintrag vor dem Wortstamm
    hits.sort(key=lambda h: (h[0], -(h[1] - h[0]), h[3]))
    used_to = -1
    pos = neg = 0
    pos_q: list[str] = []
    neg_q: list[str] = []
    for start, end, pol, _stem in hits:
        if start < used_to:  # überlappende Treffer nur einmal werten (längster zuerst)
            continue
        used_to = end
        neg_start = _negated(text, start)
        quote_start = neg_start if neg_start is not None else start
        eff = -pol if neg_start is not None else pol
        quote = text[quote_start:end]
        if eff > 0:
            pos += 1
            pos_q.append(quote)
        else:
            neg += 1
            neg_q.append(quote)
    total = pos + neg
    score = round((pos - neg) / total, 2) if total else 0.0
    label = "positiv" if score >= THRESHOLD else "negativ" if score <= -THRESHOLD else "neutral"
    if total == 0:
        rationale = "Keine Formulierung aus der Wortliste gefunden, daher neutral eingestuft."
    else:
        parts = []
        for n, kind, quotes in ((pos, "positive", pos_q), (neg, "negative", neg_q)):
            if n:
                listed = ", ".join(f"„{q}“" for q in quotes)
                parts.append(f"{n} {kind} Formulierung{'en' if n != 1 else ''} ({listed})")
        rationale = "Regelbasierte Einstufung nach Wortliste: " + " und ".join(parts) + f". Score {score:+.2f}."
    return SentimentResult(label, score, pos_q + neg_q, rationale, "lexicon", MODEL_NAME, LEXICON_VERSION,
                           LexiconSentimentSource.key)


class LexiconSentimentSource(SourceAdapter):
    """Erscheint auf der Seite Quellen als Verfahren (Grundregel 2: jede Kennzahl ist ihrer Quelle zuordenbar)."""

    key = "sentiment_lexicon"

    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            key=self.key, name=MODEL_NAME, kind="reference",
            description="Stimmung je Meldung nach einer Wortliste (Deutsch und Englisch), mit den auslösenden "
            "Formulierungen als Begründung. Kein KI-Modell, läuft ohne Kosten und ohne Schlüssel.",
            homepage="https://github.com/Marxcou/Marxcou-marktmuster-dashboard", terms_url="",
            update_interval="bei jeder neuen Meldung", delay_text="keine", requires_key=False)

    def health(self) -> Health:
        now = datetime.now(UTC)
        return Health(status="online", checked_at=now, last_success_at=now)
