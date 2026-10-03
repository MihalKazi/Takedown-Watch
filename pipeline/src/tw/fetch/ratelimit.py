"""Per-host request spacing, enforced in code (CLAUDE.md invariant 5).

Each host gets a minimum interval between request *starts*. Callers for the same host queue on a
per-host lock; different hosts never block each other.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit


def host_key(url_or_host: str) -> str:
    """Rate-limit key. www.example.com and example.com share one budget: same origin server."""
    host = urlsplit(url_or_host).hostname if "://" in url_or_host else url_or_host
    host = (host or "").lower().rstrip(".")
    return host.removeprefix("www.")


class HostRateLimiter:
    def __init__(
        self,
        default_interval: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.default_interval = default_interval
        self._clock = clock
        self._sleep = sleep
        self._intervals: dict[str, float] = {}
        self._next_allowed: dict[str, float] = {}
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def set_interval(self, host: str, seconds: float) -> None:
        """Per-outlet override. Never lowers a host below the global default."""
        self._intervals[host_key(host)] = max(seconds, self.default_interval)

    def interval(self, host: str) -> float:
        return self._intervals.get(host_key(host), self.default_interval)

    def penalise(self, host: str, seconds: float) -> None:
        """Push the host's next slot out, e.g. to honour Retry-After."""
        key = host_key(host)
        self._next_allowed[key] = max(self._next_allowed.get(key, 0.0), self._clock() + seconds)

    async def acquire(self, host: str) -> None:
        key = host_key(host)
        async with self._locks[key]:
            now = self._clock()
            wait = self._next_allowed.get(key, now) - now
            if wait > 0:
                await self._sleep(wait)
                now = self._clock()
            self._next_allowed[key] = now + self.interval(key)
