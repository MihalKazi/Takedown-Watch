"""HTTP fetcher: honest User-Agent, per-host rate limiting on every hop, bounded retries.

The fetcher is DB-agnostic. It returns every attempt it made as an `AttemptRecord`; callers persist
those as `fetch_attempt` rows.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin

import httpx

from tw.config import Settings
from tw.db.types import utcnow
from tw.fetch.classify import Outcome, classify, is_retryable
from tw.fetch.ratelimit import HostRateLimiter
from tw.log import get_logger

log = get_logger(__name__)

REDIRECT_STATUSES = {301, 302, 303, 307, 308}


@dataclass
class AttemptRecord:
    url: str
    started_at: datetime
    attempt: int
    outcome: Outcome
    final_url: str | None = None
    elapsed_ms: int | None = None
    http_status: int | None = None
    content_type: str | None = None
    response_bytes: int | None = None
    error: str | None = None


@dataclass
class FetchResult:
    url: str
    outcome: Outcome
    final_url: str | None = None
    status: int | None = None
    headers: httpx.Headers = field(default_factory=httpx.Headers)
    content: bytes = b""
    encoding: str | None = None
    attempts: list[AttemptRecord] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.outcome is Outcome.OK

    @property
    def content_type(self) -> str | None:
        return self.headers.get("content-type")

    def text(self) -> str:
        return self.content.decode(self.encoding or "utf-8", errors="replace")


def _retry_after_seconds(headers: httpx.Headers) -> float | None:
    raw = headers.get("retry-after")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        return max(0.0, (parsedate_to_datetime(raw) - utcnow()).total_seconds())
    except (TypeError, ValueError):
        return None


class Fetcher:
    def __init__(
        self,
        settings: Settings,
        limiter: HostRateLimiter,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.settings = settings
        self.limiter = limiter
        self._transport = transport
        self._sleep = sleep
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> Fetcher:
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": self.settings.effective_user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "bn,en;q=0.8",
            },
            timeout=httpx.Timeout(self.settings.http_timeout_seconds),
            follow_redirects=False,  # followed manually so every hop passes the rate limiter
            transport=self._transport,
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get(self, url: str, *, max_attempts: int | None = None) -> FetchResult:
        max_attempts = max_attempts or self.settings.http_max_attempts
        attempts: list[AttemptRecord] = []
        result = FetchResult(url=url, outcome=Outcome.CONN_ERROR)
        for n in range(1, max_attempts + 1):
            result = await self._attempt(url, n)
            attempts.append(result.attempts[0])
            if not is_retryable(result.outcome, result.status) or n == max_attempts:
                break
            delay = self.settings.http_backoff_base_seconds * 2 ** (n - 1)
            if result.outcome is Outcome.RATE_LIMITED:
                ra = _retry_after_seconds(result.headers)
                if ra is not None:
                    delay = max(delay, ra)
                delay = min(delay, self.settings.http_max_retry_after_seconds)
                self.limiter.penalise(result.final_url or url, delay)
            log.info("fetch.retry", url=url, attempt=n, outcome=str(result.outcome),
                     status=result.status, delay=round(delay, 1))
            await self._sleep(delay)
        result.attempts = attempts
        return result

    async def _attempt(self, url: str, n: int) -> FetchResult:
        assert self._client is not None, "use `async with Fetcher(...)`"
        t0 = time.monotonic()
        current = url
        record = AttemptRecord(url=url, started_at=utcnow(), attempt=n, outcome=Outcome.CONN_ERROR)
        result = FetchResult(url=url, outcome=Outcome.CONN_ERROR, attempts=[record])

        def finish(outcome: Outcome, error: str | None = None) -> FetchResult:
            record.outcome = result.outcome = outcome
            record.final_url = result.final_url = current
            record.elapsed_ms = int((time.monotonic() - t0) * 1000)
            record.error = error
            return result

        try:
            for hop in range(self.settings.http_max_redirects + 1):
                await self.limiter.acquire(current)
                if hop == 0:
                    # Stamp when the request is actually sent, not when it joined the host queue.
                    record.started_at = utcnow()
                    t0 = time.monotonic()
                async with self._client.stream("GET", current) as resp:
                    if resp.status_code in REDIRECT_STATUSES and "location" in resp.headers:
                        current = urljoin(str(resp.url), resp.headers["location"])
                        continue
                    body = bytearray()
                    async for chunk in resp.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > self.settings.http_max_bytes:
                            record.http_status = result.status = resp.status_code
                            return finish(Outcome.TOO_LARGE, f"body > {self.settings.http_max_bytes} bytes")
                    content = bytes(body)
                    record.http_status = result.status = resp.status_code
                    record.content_type = resp.headers.get("content-type")
                    record.response_bytes = len(content)
                    result.headers = resp.headers
                    result.content = content
                    result.encoding = resp.charset_encoding
                    return finish(classify(resp.status_code, resp.headers, content))
            return finish(Outcome.CONN_ERROR, "too many redirects")
        except httpx.TimeoutException as e:
            return finish(Outcome.TIMEOUT, f"{type(e).__name__}: {e}")
        except httpx.HTTPError as e:
            return finish(Outcome.CONN_ERROR, f"{type(e).__name__}: {e}")
