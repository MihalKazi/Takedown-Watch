import httpx

from tw.config import Settings
from tw.fetch.classify import Outcome
from tw.fetch.client import Fetcher
from tw.fetch.ratelimit import HostRateLimiter


async def _nosleep(_: float) -> None:
    return None


def _fetcher(handler, **overrides) -> Fetcher:
    settings = Settings(default_rate_limit_seconds=0.0, http_backoff_base_seconds=0.0, **overrides)
    return Fetcher(settings, HostRateLimiter(0.0), transport=httpx.MockTransport(handler), sleep=_nosleep)


async def test_404_is_never_retried() -> None:
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        return httpx.Response(404)

    async with _fetcher(handler) as f:
        res = await f.get("https://x.example/gone")
    assert len(calls) == 1
    assert res.outcome is Outcome.HTTP_ERROR and res.status == 404
    assert len(res.attempts) == 1


async def test_5xx_retried_up_to_max_and_every_attempt_recorded() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(502)

    async with _fetcher(handler, http_max_attempts=3) as f:
        res = await f.get("https://x.example/a")
    assert [a.attempt for a in res.attempts] == [1, 2, 3]
    assert all(a.http_status == 502 for a in res.attempts)


async def test_retry_then_success() -> None:
    n = {"i": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        n["i"] += 1
        return httpx.Response(503) if n["i"] == 1 else httpx.Response(200, text="ok")

    async with _fetcher(handler) as f:
        res = await f.get("https://x.example/a")
    assert res.ok
    assert [a.outcome for a in res.attempts] == [Outcome.HTTP_ERROR, Outcome.OK]


async def test_timeout_is_retried_and_classified() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=req)

    async with _fetcher(handler, http_max_attempts=2) as f:
        res = await f.get("https://x.example/a")
    assert res.outcome is Outcome.TIMEOUT
    assert len(res.attempts) == 2


async def test_cloudflare_challenge_is_distinct_and_not_retried() -> None:
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        return httpx.Response(
            403,
            headers={"server": "cloudflare", "content-type": "text/html"},
            text="<html><head><title>Just a moment...</title></head>"
                 "<script src='/cdn-cgi/challenge-platform/h/b/orchestrate/chl_page/v1'></script></html>",
        )

    async with _fetcher(handler) as f:
        res = await f.get("https://x.example/a")
    assert res.outcome is Outcome.CF_CHALLENGE
    assert len(calls) == 1


async def test_cf_mitigated_header_alone_is_a_challenge() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(403, headers={"cf-mitigated": "challenge"})

    async with _fetcher(handler) as f:
        assert (await f.get("https://x.example/a")).outcome is Outcome.CF_CHALLENGE


async def test_plain_403_from_cloudflare_without_challenge_markup_is_http_error() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(403, headers={"server": "cloudflare"}, text="Forbidden")

    async with _fetcher(handler) as f:
        assert (await f.get("https://x.example/a")).outcome is Outcome.HTTP_ERROR


async def test_429_honours_retry_after_and_is_recorded_as_rate_limited() -> None:
    n = {"i": 0}
    slept: list[float] = []

    async def sleep(s: float) -> None:
        slept.append(s)

    def handler(req: httpx.Request) -> httpx.Response:
        n["i"] += 1
        return httpx.Response(429, headers={"retry-after": "17"}) if n["i"] == 1 else httpx.Response(200)

    settings = Settings(default_rate_limit_seconds=0.0, http_backoff_base_seconds=1.0)
    async with Fetcher(settings, HostRateLimiter(0.0), transport=httpx.MockTransport(handler), sleep=sleep) as f:
        res = await f.get("https://x.example/a")
    assert res.ok
    assert res.attempts[0].outcome is Outcome.RATE_LIMITED
    assert slept == [17.0]


async def test_user_agent_is_honest_and_has_contact_url() -> None:
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["ua"] = req.headers["user-agent"]
        return httpx.Response(200)

    async with _fetcher(handler, contact_url="https://activaterights.org") as f:
        await f.get("https://x.example/a")
    assert seen["ua"].startswith("TakedownWatch/")
    assert "https://activaterights.org" in seen["ua"]


async def test_body_size_cap() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 2000)

    async with _fetcher(handler, http_max_bytes=1000) as f:
        res = await f.get("https://x.example/a")
    assert res.outcome is Outcome.TOO_LARGE
