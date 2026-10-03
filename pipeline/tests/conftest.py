from pathlib import Path

import pytest

from tw.config import Settings
from tw.db.models import Base
from tw.db.session import make_engine


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'tw.db').as_posix()}",
        blob_dir=tmp_path / "blobs",
        report_dir=tmp_path / "reports",
        outlets_path=tmp_path / "outlets.yaml",
        default_rate_limit_seconds=0.0,
        http_backoff_base_seconds=0.0,
        archive_interval_auth_seconds=0.0,
        archive_interval_anon_seconds=0.0,
        archive_poll_seconds=0.0,
    )


@pytest.fixture
def engine(settings: Settings):
    e = make_engine(settings.database_url)
    Base.metadata.create_all(e)
    yield e
    e.dispose()
