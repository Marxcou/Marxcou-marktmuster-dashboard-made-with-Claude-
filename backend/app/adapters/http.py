"""Gemeinsame HTTP-Schicht für Adapter: Rate-Limit, Retry mit Backoff, Circuit-Breaker und Health-Zustand.
Ein Ausfall bleibt lokal in seinem Adapter (Grundregel 6: keine Ersatzdaten, nur ein ehrlicher Status)."""
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from app.adapters.base import Health


class SourceError(Exception):
    """Die Quelle hat nicht geliefert (Netzwerk, Limit, Schlüssel, unerwartetes Format)."""


class SourceUnavailable(SourceError):
    """Circuit-Breaker offen: es wird vorübergehend nicht erneut angefragt."""


class ResilientHttp:
    def __init__(
        self, *, base_url: str, headers: dict[str, str] | None = None, rate_per_min: int = 60,
        timeout: float = 15.0, retries: int = 2, backoff: float = 1.0, breaker_threshold: int = 5,
        breaker_cooldown: float = 60.0, transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = httpx.Client(base_url=base_url, headers=headers, timeout=timeout, transport=transport)
        self._min_interval = 60.0 / max(rate_per_min, 1)
        self._retries, self._backoff = retries, backoff
        self._threshold, self._cooldown = breaker_threshold, breaker_cooldown
        self._sleep, self._clock = sleep, clock
        self._lock = threading.Lock()
        self._next_slot = 0.0
        self._failures = 0
        self._open_until = 0.0
        self.last_success_at: datetime | None = None
        self.last_error: str | None = None

    @property
    def breaker_open(self) -> bool:
        return self._clock() < self._open_until

    def _throttle(self) -> None:
        with self._lock:
            now = self._clock()
            wait = self._next_slot - now
            self._next_slot = max(now, self._next_slot) + self._min_interval
        if wait > 0:
            self._sleep(wait)

    def _fail(self, message: str) -> None:
        self.last_error = message
        self._failures += 1
        if self._failures >= self._threshold:
            self._open_until = self._clock() + self._cooldown

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        if self.breaker_open:
            raise SourceUnavailable(self.last_error or "Quelle vorübergehend pausiert")
        message = "unbekannter Fehler"
        for attempt in range(self._retries + 1):
            self._throttle()
            try:
                resp = self._client.request(method, url, **kwargs)
            except httpx.HTTPError as exc:
                message = f"Netzwerkfehler: {type(exc).__name__}"
            else:
                if resp.status_code < 400:
                    self._failures, self.last_error = 0, None
                    self.last_success_at = datetime.now(UTC)
                    return resp
                message = f"HTTP {resp.status_code}"
                if resp.status_code in (401, 403):
                    message += " (Schlüssel prüfen)"
                    break
                if resp.status_code < 500 and resp.status_code != 429:
                    break
            if attempt < self._retries:
                self._sleep(self._backoff * 2**attempt)
        self._fail(message)
        raise SourceError(message)


class ProbedHealth:
    """Health aus dem Zustand der HTTP-Schicht; ein günstiger Probe-Aufruf höchstens alle 5 Minuten."""

    http: ResilientHttp
    _probe_ttl = 300.0

    def _probe(self) -> None:  # von Adaptern überschrieben
        raise NotImplementedError

    def health(self) -> Health:
        now = datetime.now(UTC)
        stale = self.http.last_success_at is None or (now - self.http.last_success_at).total_seconds() > self._probe_ttl
        if stale and not self.http.breaker_open:
            try:
                self._probe()
            except SourceError:
                pass
        h = self.http
        if h.breaker_open:
            status = "offline"
        elif h.last_error:
            status = "degraded" if h.last_success_at else "offline"
        else:
            status = "online" if h.last_success_at else "offline"
        return Health(status=status, checked_at=now, last_success_at=h.last_success_at,  # type: ignore[arg-type]
                      message=h.last_error)
