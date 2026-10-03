from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from tw.config import REPO_ROOT
from tw.db.models import Base, Outlet
from tw.db.session import make_engine, session_scope
from tw.outlets import load_outlets, sync_outlets, write_back

YAML = """# hand comment that must survive
outlets:
  # section comment
  prothomalo:
    name: Prothom Alo   # inline comment
    language: bn
    base_url: https://www.prothomalo.com/
    tier: bangla_mass
    notes: hand-written note
  thedailystar:
    name: The Daily Star
    language: en
    base_url: https://www.thedailystar.net
    tier: english
"""


def test_repo_outlets_yaml_is_valid_and_balanced() -> None:
    outlets = load_outlets(REPO_ROOT / "outlets.yaml")
    assert len(outlets) == 18
    assert {o.language for o in outlets} == {"bn", "en"}
    assert len({o.tier for o in outlets}) == 6


def test_write_back_preserves_comments_and_hand_fields(tmp_path: Path) -> None:
    p = tmp_path / "outlets.yaml"
    p.write_text(YAML, encoding="utf-8")
    write_back(p, "prothomalo", {"rss_urls": ["https://www.prothomalo.com/feed/"], "limitations": [],
                                 "discovery": {"html_lang": "bn"}})
    text = p.read_text(encoding="utf-8")
    assert "# hand comment that must survive" in text
    assert "# section comment" in text
    assert "# inline comment" in text
    po = next(o for o in load_outlets(p) if o.slug == "prothomalo")
    assert po.rss_urls == ["https://www.prothomalo.com/feed/"]
    assert po.notes == "hand-written note"
    assert po.base_url == "https://www.prothomalo.com"


def test_write_back_refuses_invalid(tmp_path: Path) -> None:
    p = tmp_path / "outlets.yaml"
    p.write_text(YAML, encoding="utf-8")
    with pytest.raises(ValidationError):
        write_back(p, "prothomalo", {"language": "fr"})
    assert p.read_text(encoding="utf-8") == YAML


def test_sync_deactivates_rather_than_deletes(tmp_path: Path) -> None:
    p = tmp_path / "outlets.yaml"
    p.write_text(YAML, encoding="utf-8")
    engine = make_engine(f"sqlite:///{(tmp_path / 'x.db').as_posix()}")
    Base.metadata.create_all(engine)
    with session_scope(engine) as s:
        sync_outlets(s, load_outlets(p), 2.0)
    with session_scope(engine) as s:
        sync_outlets(s, [o for o in load_outlets(p) if o.slug == "prothomalo"], 2.0)
    with session_scope(engine) as s:
        rows = {o.slug: o for o in s.scalars(select(Outlet))}
    assert rows["thedailystar"].active is False
    assert rows["prothomalo"].rate_limit_seconds == 2.0
