"""Rate limiting must be demonstrable, not asserted in a comment."""

import asyncio
import time

import httpx
import pytest

from tw.config import Settings
from tw.fetch.client import Fetcher
from tw.fetch.ratelimit import HostRateLimiter, host_key


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds
        await asyncio.sleep(0)


async def test_same_host_requests_are_spaced_by_interval() -> None:
    clock = FakeClock()
    limiter = HostRateLimiter(2.0, clock=clock, sleep=clock.sleep)
    starts: list[float] = []

    async def req() -> None:
        await limiter.acquire("www.prothomalo.com")
        starts.append(clock())

    await asyncio.gather(*(req() for _ in range(5)))
    assert starts == [0.0, 2.0, 4.0, 6.0, 8.0]


async def test_different_hosts_do_not_block_each_other() -> None:
    clock = FakeClock()
    limiter = HostRateLimiter(2.0, clock=clock, sleep=clock.sleep)
    await limiter.acquire("www.prothomalo.com")
    await limiter.acquire("www.thedailystar.net")
    assert clock() == 0.0


def test_www_and_apex_share_a_budget() -> None:
    assert host_key("https://www.prothomalo.com/x") == host_key("prothomalo.com")


async def test_outlet_override_cannot_go_below_default() -> None:
    clock = FakeClock()
    limiter = HostRateLimiter(2.0, clock=clock, sleep=clock.sleep)
    limiter.set_interval("fast.example", 0.1)
    limiter.set_interval("slow.example", 5.0)
    assert limiter.interval("fast.example") == 2.0
    assert limiter.interval("slow.example") == 5.0


async def test_penalise_pushes_next_slot() -> None:
    clock = FakeClock()
    limiter = HostRateLimiter(2.0, clock=clock, sleep=clock.sleep)
    await limiter.acquire("a.example")
    limiter.penalise("a.example", 30.0)
    await limiter.acquire("a.example")
    assert clock() == 30.0


async def test_real_http_requests_to_one_host_are_spaced_in_wall_time() -> None:
    """End to end through Fetcher and a real event loop clock: 4 concurrent GETs, 0.25s interval."""
    seen: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(time.monotonic())
        return httpx.Response(200, text="ok")

    settings = Settings(default_rate_limit_seconds=0.25)
    limiter = HostRateLimiter(0.25)
    async with Fetcher(settings, limiter, transport=httpx.MockTransport(handler)) as f:
        await asyncio.gather(*(f.get(f"https://news.example/{i}") for i in range(4)))

    gaps = [b - a for a, b in zip(seen, seen[1:])]
    assert len(seen) == 4
    assert all(g >= 0.24 for g in gaps), gaps


async def test_redirect_hops_are_rate_limited_too() -> None:
    clock = FakeClock()
    limiter = HostRateLimiter(2.0, clock=clock, sleep=clock.sleep)
    hits: list[tuple[str, float]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append((request.url.path, clock()))
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "/new"})
        return httpx.Response(200, text="ok")

    async with Fetcher(Settings(), limiter, transport=httpx.MockTransport(handler)) as f:
        res = await f.get("https://news.example/old")
    assert res.ok and res.final_url == "https://news.example/new"
    assert hits == [("/old", 0.0), ("/new", 2.0)]


@pytest.mark.parametrize("n", [3])
async def test_retries_respect_rate_limit(n: int) -> None:
    clock = FakeClock()
    limiter = HostRateLimiter(2.0, clock=clock, sleep=clock.sleep)
    times: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        times.append(clock())
        return httpx.Response(503)

    settings = Settings(http_backoff_base_seconds=0.0, http_max_attempts=n)
    async with Fetcher(settings, limiter, transport=httpx.MockTransport(handler), sleep=clock.sleep) as f:
        await f.get("https://news.example/x")
    assert times == [0.0, 2.0, 4.0]


async def test_recorded_started_at_is_send_time_not_queue_time() -> None:
    """fetch_attempt.started_at is the evidence of our spacing; it must reflect the send."""
    settings = Settings(default_rate_limit_seconds=0.3)
    limiter = HostRateLimiter(0.3)
    async with Fetcher(settings, limiter, transport=httpx.MockTransport(lambda r: httpx.Response(200))) as f:
        results = await asyncio.gather(*(f.get(f"https://news.example/{i}") for i in range(3)))
    starts = sorted(r.attempts[0].started_at for r in results)
    gaps = [(b - a).total_seconds() for a, b in zip(starts, starts[1:])]
    assert all(g >= 0.29 for g in gaps), gaps
