from datetime import timedelta

from tw.recheck.backoff import SCHEDULE, delay_for_step


def test_schedule_matches_claude_md() -> None:
    assert SCHEDULE == (
        timedelta(hours=1), timedelta(hours=6), timedelta(hours=24), timedelta(days=3),
        timedelta(days=7), timedelta(days=30), timedelta(days=90), timedelta(days=365),
    )


def test_delay_for_step_in_range() -> None:
    assert delay_for_step(0) == timedelta(hours=1)
    assert delay_for_step(7) == timedelta(days=365)


def test_delay_for_step_out_of_range_is_none() -> None:
    assert delay_for_step(-1) is None
    assert delay_for_step(8) is None
