from datetime import timedelta

import pytest
from sqlalchemy import select

from tw.db.models import Job
from tw.db.queue import claim, complete, enqueue, fail
from tw.db.session import session_scope
from tw.db.types import utcnow
from tw.discover.canon import canonicalise
from tw.stats import _health


@pytest.mark.parametrize("raw,expected", [
    ("https://WWW.Prothomalo.com/bangladesh/abc?utm_source=fb&utm_medium=x", "https://www.prothomalo.com/bangladesh/abc"),
    ("https://www.prothomalo.com/a?fbclid=123#comments", "https://www.prothomalo.com/a"),
    ("https://x.example:443/a?b=2&a=1", "https://x.example/a?a=1&b=2"),
    ("https://x.example", "https://x.example/"),
    ("https://x.example/story?id=42&gclid=z", "https://x.example/story?id=42"),
    # Path case and trailing slash are significant to some servers: left alone.
    ("https://x.example/News/A/", "https://x.example/News/A/"),
])
def test_canonicalise(raw: str, expected: str) -> None:
    assert canonicalise(raw) == expected


def test_canonicalise_keeps_bangla_path() -> None:
    url = "https://www.jugantor.com/national/৮২৩৪৫৬"
    assert "৮২৩৪৫৬" in canonicalise(url) or "%E0%A7%AE" in canonicalise(url)
    assert canonicalise(canonicalise(url)) == canonicalise(url)


def test_enqueue_is_idempotent_while_open(engine) -> None:
    with session_scope(engine) as s:
        assert enqueue(s, "archive", 1) is True
        assert enqueue(s, "archive", 1) is False
        assert enqueue(s, "fetch_article", 1) is True
    with session_scope(engine) as s:
        (job,) = claim(s, "archive", "w", limit=5)
        complete(s, job)
    with session_scope(engine) as s:
        assert enqueue(s, "archive", 1) is True  # closed job does not block a new one


def test_claim_respects_run_after_and_marks_running(engine) -> None:
    with session_scope(engine) as s:
        enqueue(s, "archive", 1)
        enqueue(s, "archive", 2, delay=timedelta(hours=1))
    with session_scope(engine) as s:
        jobs = claim(s, "archive", "w1", limit=10)
        assert [j.ref_id for j in jobs] == [1]
        assert jobs[0].status == "running" and jobs[0].locked_by == "w1"
    with session_scope(engine) as s:
        assert claim(s, "archive", "w2", limit=10) == []  # running job not re-claimed


def test_stale_lock_is_reclaimed(engine) -> None:
    with session_scope(engine) as s:
        enqueue(s, "archive", 1)
    with session_scope(engine) as s:
        (j,) = claim(s, "archive", "dead-worker", limit=1)
        j.locked_at = utcnow() - timedelta(hours=2)
    with session_scope(engine) as s:
        (j,) = claim(s, "archive", "w2", limit=1)
        assert j.locked_by == "w2"


def test_fail_backs_off_then_parks_as_failed(engine) -> None:
    with session_scope(engine) as s:
        enqueue(s, "archive", 1, max_attempts=2)
    with session_scope(engine) as s:
        (j,) = claim(s, "archive", "w", limit=1)
        fail(s, j, "boom", backoff=timedelta(minutes=10))
        assert j.status == "pending" and j.run_after > utcnow() + timedelta(minutes=9)
        j.run_after = utcnow()
    with session_scope(engine) as s:
        (j,) = claim(s, "archive", "w", limit=1)
        fail(s, j, "boom", backoff=timedelta(minutes=10))
    with session_scope(engine) as s:
        j = s.scalar(select(Job))
        assert j.status == "failed" and j.attempts == 2 and j.last_error == "boom"


def test_health_flags_short_bodies_against_median() -> None:
    normal = [(3000, False)] * 20
    med, short, long_, empty, errors = _health(normal + [(50, False), (0, False), (3100, True)])
    assert med == 3000
    assert short == 2 and empty == 1 and errors == 1 and long_ == 0
