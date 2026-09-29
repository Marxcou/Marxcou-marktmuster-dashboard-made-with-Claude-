"""Handelszeiten je Börse für die Abruf-Jobs: außerhalb liefern die Quellen keine neuen Kerzen, der Job spart sich
die Anfragen (Rate-Limits der freien Tarife, Rechenzeit auf dem Server). Jede Börse hat ihre eigene Zeitzone.
Feiertage sind bewusst nicht modelliert (kein Kalender im Projekt); ein Abruf an einem Feiertag kostet nur ein paar
Anfragen und liefert nichts Falsches. Unbekannte Börsen gelten immer als aktiv."""
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

GRACE = timedelta(minutes=30)  # Nachlauf, damit die letzten Kerzen ankommen

# Börse -> (Zeitzone, Beginn, Ende). US inklusive Pre-Market ab 04:00 und After-Hours bis 20:00,
# XETRA von der Vorhandelsphase 08:00 bis zum Schluss 17:30 (mit Schlussauktion, plus Puffer bis 18:00).
SESSIONS: dict[str, tuple[ZoneInfo, time, time]] = {
    "XNYS": (ZoneInfo("America/New_York"), time(4, 0), time(20, 0)),
    "XNAS": (ZoneInfo("America/New_York"), time(4, 0), time(20, 0)),
    "XETR": (ZoneInfo("Europe/Berlin"), time(8, 0), time(18, 0)),
}


def session_active(exchange: str, now: datetime | None = None) -> bool:
    if exchange not in SESSIONS:
        return True
    tz, start_t, end_t = SESSIONS[exchange]
    local = (now or datetime.now(UTC)).astimezone(tz)
    if local.weekday() >= 5:
        return False
    start = local.replace(hour=start_t.hour, minute=start_t.minute, second=0, microsecond=0)
    end = local.replace(hour=end_t.hour, minute=end_t.minute, second=0, microsecond=0) + GRACE
    return start <= local <= end
