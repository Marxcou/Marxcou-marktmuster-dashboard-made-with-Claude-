"""Erklärtexte, Teil 1 (reine Funktionen, ohne I/O): Fakten aus den berechneten Werten, deterministische Vorlage und
Prüfung eines KI-Textes. Der KI-Text darf nichts enthalten, was nicht in den Fakten steht (Zahlen und Daten werden
gegen die Fakten geprüft), keine Empfehlungssprache und keine Links."""
import re
from datetime import datetime
from typing import Any

from app.analysis import fmt
from app.grundregeln import find_forbidden

MAX_CHARS = 2200
MIN_CHARS = 120
FREE_INTEGERS = 10  # Zahlwörter wie "zwei Szenarien" dürfen als Ziffer vorkommen
ADVICE = re.compile(r"empfehl|ratsam|einsteigen|aussteigen|einstiegs|ausstiegs|anleger sollten|sollte man",
                    re.IGNORECASE)
NUMBER = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?")
DATE = re.compile(r"\b\d{1,2}\.\d{1,2}\.(?:\d{4}|\d{2})?")
YES_NO = {True: "ja", False: "nein"}


def _dt(value: Any) -> datetime | None:
    return datetime.fromisoformat(value) if isinstance(value, str) and value else None


def _day(value: Any) -> str:
    ts = _dt(value)
    return fmt.day(ts) if ts else "unbekannt"


def _share(x: float | None, digits: int = 0) -> str:
    return "nicht verfügbar" if x is None else fmt.pct(x * 100, digits)


def pattern_facts_text(d: dict[str, Any]) -> str:
    """Alle Werte einer Erkennung als Klartext (deutsches Zahlenformat), so wie sie auch in der Oberfläche stehen."""
    conf = d["confidence"]
    lines = [
        f"Muster: {d['name']} (Zeitraster {d['timeframe']})",
        f"Lage im Chart: {_day(d['start_ts'])} bis {_day(d['end_ts'])}",
        f"Status: {d['status_label']}. {d.get('status_reason') or ''}".strip(),
        f"Richtung bei Bestätigung: {d['direction_if_confirmed']}",
        "Schlüsselpunkte:",
    ]
    lines += [f"- {k['label']}: {fmt.price(k['price'])} am {_day(k['ts'])}" for k in d["key_points"]]
    lines.append("Kriterien (Regel, tatsächlicher Wert, erfüllt):")
    lines += [f"- {c['name']}: {c['rule']}; tatsächlich: {c['actual_text']}; erfüllt: {YES_NO[bool(c['passed'])]}"
              for c in d["criteria"]]
    lines.append(f"Konfidenz-Score der Erkennung: {fmt.pct(conf['score'] * 100, 0)}")
    lines.append(f"Berechnung: {conf['method']}")
    lines += [f"- {b['name']}: Teilwert {fmt.num(b['sub_score'], 2)}, Gewicht {fmt.num(b['weight'], 2)}, "
              f"Beitrag {fmt.num(b['contribution'], 2)}" for b in conf["breakdown"]]
    lines.append(f"Bestätigungsniveau: {fmt.price(d['confirmation_level'])}")
    lines.append(f"Ungültigkeitsniveau: {fmt.price(d['invalidation_level'])}")
    lines.append("Szenarien:")
    for s in d["scenarios"]:
        hist = s.get("historical") or {}
        hist_text = ""
        if hist.get("share") is not None and hist.get("sample_size") is not None:
            hist_text = f"; historisch in {_share(hist['share'])} von {hist['sample_size']} Fällen"
        lines.append(f"- {s['title']}: {s['trigger_rule']}{hist_text}")
    lines.append(_backtest_line(d["backtest"]))
    return "\n".join(lines)


def _backtest_line(b: dict[str, Any]) -> str:
    if b.get("status") != "berechnet" or b.get("hit_rate") is None:
        return "Historische Trefferquote: nicht berechnet. Es liegt kein Backtest vor."
    parts = [f"Historische Trefferquote: {_share(b['hit_rate'])} bei {b['sample_size']} Fällen"]
    if b.get("ci_low") is not None and b.get("ci_high") is not None:
        parts.append(f"95-%-Intervall {_share(b['ci_low'])} bis {_share(b['ci_high'])}")
    if b.get("base_rate") is not None:
        parts.append(f"Basisrate über alle Handelstage {_share(b['base_rate'])}")
    if b.get("horizon_bars") is not None and b.get("min_move_pct") is not None:
        parts.append(f"Treffer = Bewegung um mindestens {fmt.num(b['min_move_pct'], 1)} % innerhalb von "
                     f"{b['horizon_bars']} Kerzen")
    if b.get("not_better_than_random"):
        parts.append("historisch nicht besser als Zufall")
    if b.get("sample_size") is not None and b["sample_size"] < 30:
        parts.append("kleine Stichprobe, geringe Aussagekraft")
    return "; ".join(parts)


def pattern_template(d: dict[str, Any]) -> str:
    """Deterministischer Text ohne KI aus denselben Werten."""
    conf = d["confidence"]
    passed = [c for c in d["criteria"] if c.get("passed")]
    text = [f"{d['name']}: erkannt im Zeitraum {_day(d['start_ts'])} bis {_day(d['end_ts'])}. "
            f"Status: {d['status_label']}."]
    if passed:
        text.append("Erkannt wurde das Muster, weil folgende Kriterien erfüllt sind: "
                    + "; ".join(c["actual_text"] for c in passed) + ".")
    text.append(f"Die Konfidenz der Erkennung beträgt {fmt.pct(conf['score'] * 100, 0)} (gewichteter Mittelwert der "
                "Teilwerte aller Kriterien, Aufschlüsselung siehe unten).")
    text.append(f"Mögliche Szenarien: Ein Schlusskurs bei {fmt.price(d['confirmation_level'])} gilt als "
                f"Bestätigungsniveau, ein Schlusskurs bei {fmt.price(d['invalidation_level'])} als "
                "Ungültigkeitsniveau. "
                "Welches Szenario eintritt, ist offen.")
    b = d["backtest"]
    if b.get("status") == "berechnet" and b.get("hit_rate") is not None:
        text.append(f"Historisch folgte auf dieses Muster in {_share(b['hit_rate'])} von {b['sample_size']} Fällen "
                    "die im Backtest definierte Bewegung."
                    + (" Das ist historisch nicht besser als Zufall." if b.get("not_better_than_random") else ""))
    else:
        text.append("Eine historische Trefferquote liegt nicht vor; sie wird nicht geschätzt.")
    text.append("Diese Beschreibung ist automatisch erstellt, kann fehlerhaft sein und ist keine Anlageberatung.")
    return " ".join(text)


def _quantile_rows(steps: list[dict[str, Any]], currency: str | None) -> list[str]:
    rows: list[str] = []
    if not steps:
        return rows
    for idx in sorted({len(steps) // 2 - 1, len(steps) - 1}):
        if idx < 0:
            continue
        s, q = steps[idx], steps[idx]["quantiles"]
        rows.append(f"- Tag {s.get('step', idx + 1)} ({_day(s['ts'])}): 95-%-Bereich {fmt.price(q['2.5'], currency)} "
                    f"bis {fmt.price(q['97.5'], currency)}, 80-%-Bereich {fmt.price(q['10'], currency)} bis "
                    f"{fmt.price(q['90'], currency)}, 50-%-Bereich {fmt.price(q['25'], currency)} bis "
                    f"{fmt.price(q['75'], currency)}, Mitte (Median) {fmt.price(q['50'], currency)}")
    return rows


def forecast_facts_text(f: dict[str, Any], symbol: str) -> str:
    cur = f.get("currency")
    m = f.get("method") or {}
    lines = [
        f"Instrument: {symbol}",
        f"Verfahren: {m.get('name', 'unbekannt')}: {m.get('description', '')}".strip(),
        f"Letzter Schlusskurs: {fmt.price(f['last_close'], cur)}, Kursdaten bis {_day(f['based_on_until'])}",
        f"Horizont: {f['horizon_bars']} Handelstage",
        "Prognosekorridor (Wahrscheinlichkeitsbereiche, keine Einzelprognose):",
    ]
    lines += _quantile_rows(f["steps"], cur)
    if f.get("is_demo"):
        lines.append("Achtung: Beispieldaten (Demo-Modus).")
    for p in f.get("pattern_scenarios") or []:
        lines.append(f"Muster {p['name']} (Szenarien aus dem Modell):")
        for s in p["scenarios"]:
            lines.append(f"- {s['title']} bei {fmt.price(s['trigger_level'])}: {s['model_probability_text']}"
                         if s.get("trigger_level") is not None else f"- {s['title']}")
    lines.append(_forecast_backtest_line(f.get("backtest") or {}))
    for c in f.get("comparison") or []:
        lines.append(f"Vergleichsverfahren: {c['name']}")
    return "\n".join(lines)


def _forecast_backtest_line(b: dict[str, Any]) -> str:
    if b.get("status") != "berechnet":
        return "Prognosegüte (Backtest): nicht berechnet. Wie zuverlässig der Korridor historisch war, ist unbekannt."
    parts = [f"Prognosegüte im Backtest: {b['sample_size']} Prognosen über je {b['horizon_bars']} Handelstage"]
    for c in b.get("coverage") or []:
        parts.append(f"Sollabdeckung {_share(c['nominal'])}, tatsächlich {_share(c['observed'], 1)}")
    if b.get("skill") is not None:
        parts.append(f"Skill gegenüber der naiven Referenz „Kurs bleibt gleich“: {fmt.num(b['skill'], 2)}")
    if b.get("verdict_text"):
        parts.append(b["verdict_text"])
    return "; ".join(parts)


def forecast_template(f: dict[str, Any], symbol: str) -> str:
    cur = f.get("currency")
    steps = f["steps"]
    last = steps[-1]
    q = last["quantiles"]
    text = [f"Für {symbol} zeigt das Verfahren {(f.get('method') or {}).get('name', 'unbekannt')} einen Korridor über "
            f"{f['horizon_bars']} Handelstage ab dem letzten Schlusskurs von {fmt.price(f['last_close'], cur)}.",
            f"Am Ende des Horizonts liegt der 50-%-Bereich zwischen {fmt.price(q['25'], cur)} und "
            f"{fmt.price(q['75'], cur)}, der 95-%-Bereich zwischen {fmt.price(q['2.5'], cur)} und "
            f"{fmt.price(q['97.5'], cur)}. Das sind Wahrscheinlichkeitsbereiche des Modells, keine Einzelprognose."]
    b = f.get("backtest") or {}
    if b.get("status") == "berechnet":
        text.append(f"Im Backtest über {b['sample_size']} Prognosen wurde geprüft, wie oft die tatsächlichen Kurse in "
                    "den Bändern lagen; die Ergebnisse stehen unter „Prognosegüte“."
                    + (f" {b['verdict_text']}" if b.get("verdict_text") else ""))
    else:
        text.append("Ein Backtest der Prognosegüte liegt nicht vor; die Zuverlässigkeit ist deshalb unbekannt.")
    text.append("Diese Beschreibung ist automatisch erstellt, kann fehlerhaft sein und ist keine Anlageberatung.")
    return " ".join(text)


def _value(token: str) -> float:
    return float(token.replace(".", "").replace(",", "."))


def validate(text: str, facts_text: str) -> str | None:
    """None, wenn der Text zulässig ist, sonst der Ablehnungsgrund. Geprüft werden Länge, Empfehlungssprache,
    Links und dass jede Zahl und jedes Datum aus den Fakten stammt."""
    if not MIN_CHARS <= len(text) <= MAX_CHARS:
        return "Länge außerhalb des zulässigen Bereichs"
    if find_forbidden(text) or ADVICE.search(text):
        return "enthält unzulässige Sprache"
    if re.search(r"https?://|www\.", text):
        return "enthält einen Link"
    facts_dates = {m.group(0)[:5] for m in DATE.finditer(facts_text)}
    facts_dates |= {m.group(0) for m in DATE.finditer(facts_text)}
    for m in DATE.finditer(text):
        if m.group(0) not in facts_dates and m.group(0)[:5] not in facts_dates:
            return f"Datum {m.group(0)} steht nicht in den Fakten"
    facts_numbers = {_value(m.group(0)) for m in NUMBER.finditer(DATE.sub(" ", facts_text))}
    for m in NUMBER.finditer(DATE.sub(" ", text)):
        v = _value(m.group(0))
        if v not in facts_numbers and not (float(v).is_integer() and 0 <= v <= FREE_INTEGERS):
            return f"Zahl {m.group(0)} steht nicht in den Fakten"
    return None
