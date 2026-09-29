"""Handelszeiten für die Abruf-Jobs: außerhalb liefern die US-Quellen keine neuen Kerzen, der Job spart sich die
Anfragen (Rate-Limits der freien Tarife, Rechenzeit auf dem Server). Feiertage sind bewusst nicht modelliert;
ein Abruf an einem Feiertag kostet nur ein paar Anfragen und liefert nichts Falsches."""
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
# Pre-Market ab 04:00, After-Hours bis 20:00, dazu eine halbe Stunde Nachlauf, damit die letzten Kerzen ankommen
US_OPEN = time(4, 0)
US_CLOSE = time(20, 0)
GRACE = timedelta(minutes=30)


def us_session_active(now: datetime | None = None) -> bool:
    local = (now or datetime.now(UTC)).astimezone(NY)
    if local.weekday() >= 5:
        return False
    start = local.replace(hour=US_OPEN.hour, minute=US_OPEN.minute, second=0, microsecond=0)
    end = local.replace(hour=US_CLOSE.hour, minute=US_CLOSE.minute, second=0, microsecond=0) + GRACE
    return start <= local <= end
