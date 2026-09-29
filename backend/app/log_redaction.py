"""Schlüssel dürfen weder in Logs noch in gespeicherten Statustexten landen (Regel: Schlüssel nur in .env).

Zwei Schutzschichten: (1) bekannte Geheimwerte aus den Einstellungen werden überall ersetzt, (2) URL-Parameter mit
typischen Schlüsselnamen (token, apikey, ...) werden unabhängig vom Wert ersetzt. Zusätzlich ist das
HTTP-Client-Logging (httpx/httpcore), das komplette Anfrage-URLs ausgibt, auf WARNING gestellt."""
import logging
import re
import sys

from app.config import get_settings

MASK = "***"
_MIN_SECRET_LEN = 6
_NAME_HINTS = ("key", "secret", "token", "password")
_PARAM_RE = re.compile(
    r"(?i)([?&\s\"'])(token|api_?key|api_?token|access_?token|key|secret|password)=([^&\s\"']+)")
_installed = False


def secret_values() -> list[str]:
    """Alle konfigurierten Geheimwerte (aus .env), längste zuerst, damit Teilwerte nichts übrig lassen."""
    values = {
        v.strip() for name, v in get_settings().model_dump().items()
        if isinstance(v, str) and any(h in name for h in _NAME_HINTS) and len(v.strip()) >= _MIN_SECRET_LEN
    }
    return sorted(values, key=len, reverse=True)


def redact(text: str) -> str:
    for secret in secret_values():
        text = text.replace(secret, MASK)
    return _PARAM_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}={MASK}", text)


def _plain_args(args: object) -> bool:
    """Nur Tupel aus Text und Zahlen dürfen einzeln bereinigt werden; alles andere (Objekte, Ausnahmen, Mappings)
    wird erst formatiert, weil erst der Text zeigt, ob ein Geheimwert darin steckt."""
    plain = (str, int, float, bool, type(None))
    return isinstance(args, tuple) and len(args) > 0 and all(isinstance(a, plain) for a in args)


def install() -> None:
    """Einmal je Prozess aufrufen (API, Worker, Backtest-Job): jeder Log-Eintrag wird beim Erzeugen bereinigt,
    auch Tracebacks. Gilt für alle Logger und Handler, auch für die von uvicorn."""
    global _installed
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    if _installed:
        return
    _installed = True
    factory = logging.getLogRecordFactory()

    def make_record(*args, **kwargs):  # type: ignore[no-untyped-def]
        rec = factory(*args, **kwargs)
        try:
            if _plain_args(rec.args):
                # Struktur der Argumente erhalten: uvicorns Zugriffs-Formatierer entpackt record.args selbst
                rec.msg = redact(str(rec.msg))
                rec.args = tuple(redact(a) if isinstance(a, str) else a for a in rec.args)  # type: ignore[union-attr]
            else:
                rec.msg, rec.args = redact(rec.getMessage()), None
            if rec.exc_info and not rec.exc_text:
                rec.exc_text = redact(logging.Formatter().formatException(rec.exc_info))
            elif rec.exc_text:
                rec.exc_text = redact(rec.exc_text)
            if rec.stack_info:
                rec.stack_info = redact(rec.stack_info)
        except Exception:  # Logging darf nie die Anwendung stören
            rec.msg, rec.args = "[Logeintrag wegen Redaktionsfehler unterdrückt]", None
            rec.exc_info = rec.exc_text = None
        return rec

    logging.setLogRecordFactory(make_record)
    # Fehler ausserhalb von Logging (z. B. unbehandelte Ausnahme im Hauptthread) laufen über excepthook

    def safe_hook(exc_type, exc, tb):  # type: ignore[no-untyped-def]
        import traceback
        sys.stderr.write(redact("".join(traceback.format_exception(exc_type, exc, tb))))

    sys.excepthook = safe_hook
