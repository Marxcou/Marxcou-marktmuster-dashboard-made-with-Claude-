"""Worker-Prozess: Scheduler für Abrufe und Berechnungen. Phase 1A liefert nur das Gerüst:
den Scheduler, den Health-Check-Job für alle registrierten Adapter und den Einhängepunkt für weitere Jobs."""
import logging
from collections.abc import Callable

from apscheduler.schedulers.blocking import BlockingScheduler

from app.adapters.registry import load_builtin_adapters
from app.db import SessionLocal
from app.sources_sync import sync_sources

log = logging.getLogger("worker")

# Workstreams 1B/2x/3x hängen ihre Jobs hier ein: (Funktion, Intervall in Sekunden)
JOBS: list[tuple[Callable[[], None], int]] = []


def health_job() -> None:
    with SessionLocal() as db:
        sync_sources(db)


def build_scheduler() -> BlockingScheduler:
    sched = BlockingScheduler(timezone="UTC")
    sched.add_job(health_job, "interval", seconds=60, id="source-health", max_instances=1)
    for fn, seconds in JOBS:
        sched.add_job(fn, "interval", seconds=seconds, id=fn.__name__, max_instances=1)
    return sched


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    load_builtin_adapters()
    log.info("Worker gestartet")
    build_scheduler().start()


if __name__ == "__main__":
    main()
