"""Zahlen- und Datumsformat de-DE für die Erklärtexte (Zeitzone Europe/Berlin)."""
from datetime import datetime
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
CURRENCY = {"EUR": "€", "USD": "$"}


def num(x: float, digits: int = 2) -> str:
    s = f"{x:,.{digits}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def price(x: float, currency: str | None = None) -> str:
    """Kurs mit Währungszeichen; ohne Währung (Mustererkennung, instrumentenneutral) nur die Zahl,
    unter 1 mit vier Nachkommastellen."""
    if currency is None:
        return num(x, 4 if abs(x) < 1 else 2)
    return f"{num(x)} {CURRENCY.get(currency, currency)}"


def pct(x: float, digits: int = 2) -> str:
    return f"{num(x, digits)} %"


def day(ts: datetime) -> str:
    return ts.astimezone(BERLIN).strftime("%d.%m.%Y")


def stamp(ts: datetime, timeframe: str) -> str:
    return day(ts) if timeframe == "1d" else ts.astimezone(BERLIN).strftime("%d.%m.%Y %H:%M")
