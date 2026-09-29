"""Zahlen- und Datumsformat de-DE für die Erklärtexte der Ereignisse (Zeitzone Europe/Berlin)."""
from datetime import datetime
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
CURRENCY = {"EUR": "€", "USD": "$"}


def num(x: float, digits: int = 2) -> str:
    s = f"{x:,.{digits}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def price(x: float, currency: str) -> str:
    return f"{num(x)} {CURRENCY.get(currency, currency)}"


def day(ts: datetime) -> str:
    return ts.astimezone(BERLIN).strftime("%d.%m.%Y")


def stamp(ts: datetime, timeframe: str) -> str:
    return day(ts) if timeframe == "1d" else ts.astimezone(BERLIN).strftime("%d.%m.%Y %H:%M")
