"""M2 recheck backoff schedule. See CLAUDE.md "Core design principle: age at change".

Every captured article is rechecked on exponential backoff from first capture:
T+1h -> T+6h -> T+24h -> T+3d -> T+7d -> T+30d -> T+90d -> T+365d

`step` is the number of *prior* snapshots for the article beyond the first (i.e. how many
rechecks already happened). step=0 means "schedule the first recheck after the first snapshot".
Once the schedule is exhausted, no further recheck is scheduled (the article has aged out; a
future milestone may revisit long-tail cadence).
"""

from __future__ import annotations

from datetime import timedelta

SCHEDULE: tuple[timedelta, ...] = (
    timedelta(hours=1),
    timedelta(hours=6),
    timedelta(hours=24),
    timedelta(days=3),
    timedelta(days=7),
    timedelta(days=30),
    timedelta(days=90),
    timedelta(days=365),
)


def delay_for_step(step: int) -> timedelta | None:
    """Delay from *first capture* for the step-th recheck, or None if the schedule is exhausted."""
    if step < 0 or step >= len(SCHEDULE):
        return None
    return SCHEDULE[step]
