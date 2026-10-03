import pytest

from tw.annotate import add_annotation, list_annotations, set_review
from tw.db.models import Article, Event, Outlet
from tw.db.session import session_scope
from tw.db.types import utcnow
from tw.events import EventDraft, HEADLINE_CHANGED, write_event


def _seed_event(s) -> int:
    now = utcnow()
    o = Outlet(slug="ex", name="Ex", language="en", base_url="https://x.example", tier="english")
    s.add(o)
    s.flush()
    art = Article(outlet_id=o.id, canonical_url="https://x.example/a", url_hash="h", first_seen=now, last_seen=now)
    s.add(art)
    s.flush()
    ev = write_event(s, art, EventDraft(HEADLINE_CHANGED, "confirmed"), detected_at=now)
    return ev.id


def test_annotation_requires_existing_event(engine) -> None:
    with session_scope(engine) as s, pytest.raises(ValueError, match="no event"):
        add_annotation(s, 999, "analyst", "a claim")


def test_add_and_list_annotations(engine) -> None:
    with session_scope(engine) as s:
        event_id = _seed_event(s)
        add_annotation(s, event_id, "analyst-a", "first note")
        add_annotation(s, event_id, "analyst-b", "second note", review_state="published")

    with session_scope(engine) as s:
        anns = list_annotations(s, event_id)
        assert [a.author for a in anns] == ["analyst-a", "analyst-b"]
        assert anns[1].review_state == "published"
        assert anns[0].review_state == "draft"


def test_annotation_rejects_bad_review_state(engine) -> None:
    with session_scope(engine) as s:
        event_id = _seed_event(s)
        with pytest.raises(ValueError, match="review_state"):
            add_annotation(s, event_id, "analyst", "note", review_state="nope")


def test_set_review_updates_event_not_annotation(engine) -> None:
    with session_scope(engine) as s:
        event_id = _seed_event(s)
        set_review(s, event_id, "editor", "confirmed")

    with session_scope(engine) as s:
        ev = s.get(Event, event_id)
        assert ev.reviewed_by == "editor"
        assert ev.review_decision == "confirmed"
        assert ev.reviewed_at is not None
        assert list_annotations(s, event_id) == []  # review is workflow state, not an annotation


def test_set_review_rejects_bad_decision(engine) -> None:
    with session_scope(engine) as s:
        event_id = _seed_event(s)
        with pytest.raises(ValueError, match="decision"):
            set_review(s, event_id, "editor", "nope")
