"""Deutsche Formatierung für die Erklärtexte (de-DE, Europe/Berlin)."""
from datetime import datetime
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")


def num(x: float, decimals: int = 2) -> str:
    s = f"{x:,.{decimals}f}"
    return s.replace(",", " ").replace(".", ",").replace(" ", ".")


def price(x: float) -> str:
    return num(x, 4 if abs(x) < 1 else 2)


def pct(x: float, decimals: int = 2) -> str:
    return f"{num(x, decimals)} %"


def date(ts: datetime, timeframe: str) -> str:
    local = ts.astimezone(BERLIN)
    if timeframe == "1d":
        # Tageskerzen tragen das Handelsdatum (UTC-Mitternacht); das Datum selbst wird nicht verschoben.
        return ts.strftime("%d.%m.%Y")
    return local.strftime("%d.%m.%Y %H:%M")
