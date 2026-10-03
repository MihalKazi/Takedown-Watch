"""Internet Archive Save Page Now (SPN2) client.

Authenticated mode (archive.org S3-style keys): POST /save, then poll /save/status/{job_id}.
Anonymous mode: GET /save/{url}; the capture location comes back in Content-Location, the redirect
target, or as an spn2 job id in the page, which is then polled the same way. As of 2026-09 the
Archive answers anonymous requests with 401 "You need to be logged in to use Save Page Now.", so
in practice keys are required; the anonymous path is kept in case that policy changes.

Every request goes through the shared per-host rate limiter; SPN is slow and strictly rate-limited.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Literal

import httpx

from tw.config import Settings
from tw.fetch.ratelimit import HostRateLimiter

SPN = "https://web.archive.org"
_WAYBACK_RE = re.compile(r"/web/(\d{14})/(.+)$")
_JOB_RE = re.compile(r"spn2-[0-9a-f]{20,}")
_RATE_LIMIT_ERRORS = ("too-many", "session-limit", "rate-limit", "overloaded")


@dataclass
class SpnResult:
    outcome: Literal["ok", "pending", "error", "rate_limited", "timeout", "auth_required"]
    archive_url: str | None = None
    job_id: str | None = None
    error: str | None = None


def wayback_url(timestamp: str, original: str) -> str:
    return f"{SPN}/web/{timestamp}/{original}"


def _from_location(loc: str | None) -> str | None:
    if loc and (m := _WAYBACK_RE.search(loc)):
        return wayback_url(m.group(1), m.group(2))
    return None


class SpnClient:
    def __init__(self, settings: Settings, limiter: HostRateLimiter, *,
                 transport: httpx.AsyncBaseTransport | None = None, sleep=asyncio.sleep) -> None:
        self.settings = settings
        self.limiter = limiter
        self.sleep = sleep
        key, secret = settings.ia_access_key, settings.ia_secret_key
        self.mode: Literal["auth", "anon"] = "auth" if key and secret else "anon"
        headers = {"User-Agent": settings.effective_user_agent, "Accept": "application/json"}
        if self.mode == "auth":
            headers["Authorization"] = f"LOW {key.get_secret_value()}:{secret.get_secret_value()}"
        limiter.set_interval("web.archive.org", settings.archive_interval_auth_seconds
                             if self.mode == "auth" else settings.archive_interval_anon_seconds)
        self._client = httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(120.0),
                                         follow_redirects=False, transport=transport)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, url: str, **kw) -> httpx.Response:
        await self.limiter.acquire(url)
        return await self._client.request(method, url, **kw)

    @staticmethod
    def _message(r: httpx.Response) -> str:
        try:
            data = r.json()
        except ValueError:
            return r.text[:300]
        return str(data.get("message") or data.get("status_ext") or data)[:300]

    async def save(self, url: str) -> SpnResult:
        try:
            if self.mode == "auth":
                r = await self._request("POST", f"{SPN}/save", data={"url": url, "skip_first_archive": "1"})
                if r.status_code == 429:
                    return SpnResult("rate_limited", error="HTTP 429")
                if r.status_code in (401, 403):
                    return SpnResult("auth_required", error=f"HTTP {r.status_code}: {self._message(r)}")
                data = r.json() if "json" in r.headers.get("content-type", "") else {}
                if job := data.get("job_id"):
                    return await self.wait(job)
                return self._error(data.get("status_ext") or data.get("message") or f"HTTP {r.status_code}")
            r = await self._request("GET", f"{SPN}/save/{url}")
            if r.status_code == 429:
                return SpnResult("rate_limited", error="HTTP 429")
            if r.status_code in (401, 403):
                return SpnResult("auth_required", error=f"HTTP {r.status_code}: {self._message(r)}")
            done = _from_location(r.headers.get("content-location")) or _from_location(r.headers.get("location"))
            if done:
                return SpnResult("ok", archive_url=done)
            if m := _JOB_RE.search(r.text):
                return await self.wait(m.group(0))
            return SpnResult("error", error=f"HTTP {r.status_code}: {self._message(r)}")
        except httpx.TimeoutException as e:
            return SpnResult("timeout", error=f"{type(e).__name__}: {e}")
        except httpx.HTTPError as e:
            return SpnResult("error", error=f"{type(e).__name__}: {e}")

    async def status(self, job_id: str) -> SpnResult:
        try:
            r = await self._request("GET", f"{SPN}/save/status/{job_id}")
        except httpx.HTTPError as e:
            return SpnResult("pending", job_id=job_id, error=f"{type(e).__name__}: {e}")
        if r.status_code == 429:
            return SpnResult("pending", job_id=job_id, error="HTTP 429 on status")
        try:
            data = r.json()
        except ValueError:
            return SpnResult("pending", job_id=job_id, error=f"HTTP {r.status_code}: non-JSON status")
        st = data.get("status")
        if st == "success" and data.get("timestamp") and data.get("original_url"):
            return SpnResult("ok", archive_url=wayback_url(data["timestamp"], data["original_url"]), job_id=job_id)
        if st == "pending":
            return SpnResult("pending", job_id=job_id)
        return self._error(data.get("status_ext") or data.get("message") or str(data), job_id)

    async def wait(self, job_id: str) -> SpnResult:
        waited = 0.0
        while True:
            res = await self.status(job_id)
            if res.outcome != "pending" or waited >= self.settings.archive_poll_timeout_seconds:
                return res
            await self.sleep(self.settings.archive_poll_seconds)
            waited += self.settings.archive_poll_seconds

    @staticmethod
    def _error(msg: str, job_id: str | None = None) -> SpnResult:
        kind = "rate_limited" if any(k in msg.lower() for k in _RATE_LIMIT_ERRORS) else "error"
        return SpnResult(kind, job_id=job_id, error=msg[:2000])
