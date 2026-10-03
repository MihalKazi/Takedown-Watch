"""Save Page Now client and queue drain, against a mocked web.archive.org."""

import httpx
from pydantic import SecretStr
from sqlalchemy import select

from tw.archive.run import coverage, drain
from tw.archive.spn import SpnClient
from tw.db.models import ArchiveAttempt, Article, FetchAttempt, Job, Outlet, Snapshot
from tw.db.queue import enqueue
from tw.db.session import session_scope
from tw.db.types import utcnow
from tw.fetch.ratelimit import HostRateLimiter

URL = "https://www.example-news.com/a"
TS = "20260924010203"


def seed(engine, n: int = 1) -> list[int]:
    now = utcnow()
    ids = []
    with session_scope(engine) as s:
        o = Outlet(slug="ex", name="Ex", language="bn", base_url="https://www.example-news.com", tier="bangla_mass")
        s.add(o)
        s.flush()
        for i in range(n):
            a = Article(outlet_id=o.id, canonical_url=f"{URL}{i}", url_hash=f"{i:064d}", first_seen=now, last_seen=now)
            s.add(a)
            s.flush()
            fa = FetchAttempt(outlet_id=o.id, article_id=a.id, kind="article", url=a.canonical_url, vantage="t",
                              started_at=now, outcome="ok", http_status=200)
            s.add(fa)
            s.flush()
            snap = Snapshot(article_id=a.id, fetch_attempt_id=fa.id, fetched_at=now, http_status=200, vantage="t",
                            final_url=a.canonical_url, body_length=0, body_hash="0" * 64, headline_hash="0" * 64,
                            byline_hash="0" * 64, extractor_version="x", normaliser_version="1")
            s.add(snap)
            s.flush()
            enqueue(s, "archive", snap.id)
            ids.append(snap.id)
    return ids


async def _nosleep(_: float) -> None:
    return None


def client(settings, handler, **kw) -> SpnClient:
    for k, v in kw.items():
        setattr(settings, k, v)
    return SpnClient(settings, HostRateLimiter(0.0), transport=httpx.MockTransport(handler), sleep=_nosleep)


async def test_authenticated_submit_and_poll(settings, engine) -> None:
    seed(engine)
    seen: dict = {"polls": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["auth"] = req.headers.get("authorization")
        if req.method == "POST" and req.url.path == "/save":
            seen["form"] = req.content.decode()
            return httpx.Response(200, json={"url": URL, "job_id": "spn2-" + "a" * 40})
        if req.url.path.startswith("/save/status/"):
            seen["polls"] += 1
            if seen["polls"] < 2:
                return httpx.Response(200, json={"status": "pending"})
            return httpx.Response(200, json={"status": "success", "timestamp": TS, "original_url": URL + "0"})
        return httpx.Response(404)

    spn = client(settings, handler, ia_access_key=SecretStr("KEY"), ia_secret_key=SecretStr("SECRET"))
    counts = await drain(settings, engine, client=spn)
    assert spn.mode == "auth"
    assert seen["auth"] == "LOW KEY:SECRET"
    assert "url=" in seen["form"]
    assert counts["ok"] == 1
    with session_scope(engine) as s:
        a = s.scalar(select(ArchiveAttempt))
        assert a.outcome == "ok" and a.mode == "auth"
        assert a.archive_url == f"https://web.archive.org/web/{TS}/{URL}0"
        assert a.completed_at is not None
        assert s.scalar(select(Job.status).where(Job.kind == "archive")) == "done"
    assert coverage(engine) == (1, 1)


async def test_anonymous_uses_content_location(settings, engine) -> None:
    seed(engine)

    def handler(req: httpx.Request) -> httpx.Response:
        assert "authorization" not in req.headers
        assert req.url.path.startswith("/save/https://")
        return httpx.Response(200, headers={"content-location": f"/web/{TS}/{URL}0"})

    counts = await drain(settings, engine, client=client(settings, handler))
    assert counts["ok"] == 1
    assert coverage(engine) == (1, 1)


async def test_rate_limit_stops_run_and_keeps_jobs_queued(settings, engine) -> None:
    seed(engine, n=3)
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        return httpx.Response(429)

    counts = await drain(settings, engine, client=client(settings, handler))
    assert counts == {"rate_limited": 1}
    assert len(calls) == 1
    with session_scope(engine) as s:
        statuses = sorted(s.scalars(select(Job.status).where(Job.kind == "archive")))
        assert statuses == ["pending", "pending", "pending"]
        retry = s.scalar(select(Job).where(Job.attempts == 1))
        assert retry.run_after > utcnow()
    assert coverage(engine) == (3, 0)


async def test_pending_is_resolved_by_next_run(settings, engine) -> None:
    seed(engine)
    state = {"done": False}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST":
            return httpx.Response(200, json={"job_id": "spn2-" + "b" * 40})
        if state["done"]:
            return httpx.Response(200, json={"status": "success", "timestamp": TS, "original_url": URL + "0"})
        return httpx.Response(200, json={"status": "pending"})

    kw = dict(ia_access_key=SecretStr("K"), ia_secret_key=SecretStr("S"), archive_poll_timeout_seconds=0.0)
    first = await drain(settings, engine, client=client(settings, handler, **kw))
    assert first["pending"] == 1
    assert coverage(engine) == (1, 0)
    state["done"] = True
    second = await drain(settings, engine, client=client(settings, handler, **kw))
    assert second["resolved_ok"] == 1
    assert coverage(engine) == (1, 1)


async def test_spn_error_retries_with_backoff(settings, engine) -> None:
    seed(engine)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "error", "status_ext": "error:blocked-url"})

    kw = dict(ia_access_key=SecretStr("K"), ia_secret_key=SecretStr("S"))
    counts = await drain(settings, engine, client=client(settings, handler, **kw))
    assert counts["error"] == 1
    with session_scope(engine) as s:
        a = s.scalar(select(ArchiveAttempt))
        assert a.outcome == "error" and "blocked-url" in a.error
        job = s.scalar(select(Job).where(Job.kind == "archive"))
        assert job.status == "pending" and job.attempts == 1


async def test_login_required_stops_run_without_burning_attempts(settings, engine) -> None:
    seed(engine, n=3)
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        return httpx.Response(401, json={"message": "You need to be logged in to use Save Page Now."})

    counts = await drain(settings, engine, client=client(settings, handler))
    assert counts["auth_required"] == 1 and counts["stopped_auth_required"] == 1
    assert len(calls) == 1
    with session_scope(engine) as s:
        jobs = list(s.scalars(select(Job).where(Job.kind == "archive")))
        assert all(j.status == "pending" and j.attempts == 0 for j in jobs)
        a = s.scalar(select(ArchiveAttempt))
        assert a.outcome == "auth_required" and "logged in" in a.error
