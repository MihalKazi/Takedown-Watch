"""Export publication policy: no per-outlet figures; groups under MIN_GROUP_OUTLETS are suppressed."""

import json

import httpx

from tw.crawl import crawl
from tw.export import MIN_GROUP_OUTLETS, build, write

from test_crawl import OUTLETS, handler


def _dump(files) -> dict:
    return {name: m.model_dump(mode="json") for name, m in files.items()}


async def test_single_outlet_dataset_is_fully_suppressed(settings, engine, tmp_path) -> None:
    settings.outlets_path.write_text(OUTLETS, encoding="utf-8")
    await crawl(settings, engine, None, transport=httpx.MockTransport(handler))
    d = _dump(build(engine, settings))

    assert MIN_GROUP_OUTLETS == 3
    cov = d["coverage.json"]
    assert cov["outlets_contributing"] == 1
    for g in cov["groups"]:
        assert g["suppressed"] is True
        assert all(g[k] is None for k in ("outlets_contributing", "articles_captured", "snapshots", "archive_rate",
                                          "capture_success_rate"))
    for h in d["extraction-health.json"]["groups"]:
        assert h["status"] is None and h["outlets_contributing"] is None
    assert d["capture-volume.json"]["suppressed"] is True
    assert d["capture-volume.json"]["series"] == []


async def test_outlets_file_carries_no_figures(settings, engine) -> None:
    settings.outlets_path.write_text(OUTLETS, encoding="utf-8")
    await crawl(settings, engine, None, transport=httpx.MockTransport(handler))
    row = _dump(build(engine, settings))["outlets.json"]["outlets"][0]
    assert set(row) == {"slug", "name", "language", "tier", "base_url"}


def test_written_files_are_stable_json(settings, engine, tmp_path) -> None:
    out = write(build(engine, settings), tmp_path)
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["schema_version"] == "1.0.0"
    assert sorted(meta["files"]) == sorted(p.name for p in out.glob("*.json"))


# --- complementary suppression -------------------------------------------------------------------

import itertools
import random

from tw.export import TIERS, _OutletFigures, _groups, suppression_plan


def _cohort(spec: list[tuple[str, str, str, bool]]) -> list[_OutletFigures]:
    return [_OutletFigures(slug, slug, lang, tier, f"https://{slug}.example", True, True, snapshots=int(on))
            for slug, lang, tier, on in spec]


# The cohort as captured on 2026-09-24: English (5 contributing) minus the English-language tier
# (4 contributing) would leave a single outlet's figures.
REAL = [
    ("prothomalo", "bn", "bangla_mass", True), ("jugantor", "bn", "bangla_mass", True),
    ("samakal", "bn", "bangla_mass", True), ("bd-pratidin", "bn", "bangla_mass", True),
    ("kalerkantho", "bn", "bangla_mass", False), ("dailyamardesh", "bn", "bangla_other", True),
    ("dailyinqilab", "bn", "bangla_other", True), ("dailynayadiganta", "bn", "bangla_other", False),
    ("thedailystar", "en", "english", True), ("dhakatribune", "en", "english", True),
    ("tbsnews", "en", "english", True), ("newagebd", "en", "english", True),
    ("bdnews24", "en", "online_native", True), ("banglatribune", "bn", "online_native", True),
    ("jagonews24", "bn", "online_native", False), ("bssnews", "en", "state_wire", False),
    ("netra", "en", "independent", False), ("thedissent", "en", "independent", False),
]


def _leaks(groups, plan, k=3) -> list[str]:
    sets = {(g, key): frozenset(f.slug for f in fs) for g, key, fs in groups}
    contrib = {f.slug for _, _, fs in groups for f in fs if f.snapshots > 0}
    pub = [gk for gk in sets if gk not in plan]
    found = []
    for a in pub:
        subs = [b for b in pub if b != a and sets[b] < sets[a]]
        for r in range(1, len(subs) + 1):
            for fam in itertools.combinations(subs, r):
                if any(sets[x] & sets[y] for x, y in itertools.combinations(fam, 2)):
                    continue
                res = sets[a] - frozenset().union(*(sets[b] for b in fam))
                c = len(res & contrib)
                if res and (0 < c < k or (c == 0 and len(res) < k)):
                    found.append(f"{a} - {fam}")
    return found


def test_real_cohort_english_tier_withheld_complementarily() -> None:
    groups = _groups(_cohort(REAL))
    plan = suppression_plan(groups)
    assert plan[("tier", "english")] == "complementary"
    assert plan[("tier", "state_wire")] == "small_group"
    assert ("language", "en") not in plan and ("all", "all") not in plan
    assert _leaks(groups, plan) == []


def test_no_residual_leak_on_random_cohorts() -> None:
    rng = random.Random(7)
    for _ in range(200):
        spec = [(f"o{i}", rng.choice(["bn", "en"]), rng.choice(TIERS), rng.random() < 0.7) for i in range(18)]
        groups = _groups(_cohort(spec))
        plan = suppression_plan(groups)
        assert _leaks(groups, plan) == [], spec
