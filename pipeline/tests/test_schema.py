from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError, StatementError

from tw.config import PIPELINE_ROOT
from tw.db.models import Base, Job, Outlet
from tw.db.session import make_engine, session_scope


def _cfg(url: str) -> Config:
    cfg = Config(str(PIPELINE_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PIPELINE_ROOT / "migrations"))
    cfg.attributes["database_url"] = url
    cfg.attributes["configure_logger"] = False
    return cfg


def test_migration_matches_models(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 't.db').as_posix()}"
    command.upgrade(_cfg(url), "head")
    command.check(_cfg(url))  # raises if models drifted from migrations
    tables = set(inspect(make_engine(url)).get_table_names())
    assert {"outlet", "article", "article_url", "fetch_attempt", "snapshot", "archive_attempt",
            "listing", "listing_entry", "robots_snapshot", "job"} <= tables


def test_no_interpretation_columns_on_machine_tables() -> None:
    """CLAUDE.md invariant 1."""
    banned = {"reason", "motive", "cause", "is_censorship"}
    for table in Base.metadata.tables.values():
        assert not banned & set(table.columns.keys()), table.name


@pytest.fixture
def engine(tmp_path: Path):
    e = make_engine(f"sqlite:///{(tmp_path / 'u.db').as_posix()}")
    Base.metadata.create_all(e)
    return e


def _outlet() -> Outlet:
    return Outlet(slug="x", name="X", language="bn", base_url="https://x.example", tier="bangla_mass")


def test_datetimes_roundtrip_as_utc(engine) -> None:
    dhaka = timezone(timedelta(hours=6))
    with session_scope(engine) as s:
        s.add(_outlet())
        s.flush()
        s.add(Job(kind="archive", ref_id=1, run_after=datetime(2026, 9, 24, 12, 0, tzinfo=dhaka),
                  created_at=datetime.now(UTC)))
    with session_scope(engine) as s:
        job = s.scalars(select(Job)).one()
        assert job.run_after == datetime(2026, 9, 24, 6, 0, tzinfo=UTC)
        assert job.run_after.tzinfo is not None


def test_naive_datetime_refused(engine) -> None:
    with pytest.raises(StatementError, match="naive datetime"), session_scope(engine) as s:
        s.add(Job(kind="archive", ref_id=1, run_after=datetime(2026, 9, 24), created_at=datetime.now(UTC)))


def test_one_open_job_per_kind_and_ref(engine) -> None:
    now = datetime.now(UTC)
    with session_scope(engine) as s:
        s.add(Job(kind="archive", ref_id=7, run_after=now, created_at=now, status="done"))
        s.add(Job(kind="archive", ref_id=7, run_after=now, created_at=now))
    with pytest.raises(IntegrityError), session_scope(engine) as s:
        s.add(Job(kind="archive", ref_id=7, run_after=now, created_at=now))
