"""Extraction against real article HTML saved from the outlets (tests/fixtures/*/*.html.gz)."""

import gzip
import re
import unicodedata
from pathlib import Path

import pytest

from tw.extract.extractor import EXTRACTOR_VERSION, extract
from tw.extract.hashing import text_hash
from tw.extract.normalise import normalise

FIXTURES = Path(__file__).parent / "fixtures"
BENGALI = re.compile(r"[ঀ-৿]")


def load(name: str) -> tuple[bytes, str]:
    html = gzip.decompress((FIXTURES / f"{name}.html.gz").read_bytes())
    url = (FIXTURES / f"{name}.url").read_text(encoding="utf-8").strip()
    return html, url


BN = ["bn/prothomalo-1", "bn/prothomalo-2"]


@pytest.mark.parametrize("name", BN)
def test_real_bangla_article_extracts(name: str) -> None:
    html, url = load(name)
    e = extract(html, url)
    assert e.headline and BENGALI.search(e.headline)
    assert e.byline and BENGALI.search(e.byline)
    assert e.body_text and len(e.body_text) > 1000
    bn_share = len(BENGALI.findall(e.body_text)) / len(re.sub(r"\s", "", e.body_text))
    assert bn_share > 0.8, bn_share
    assert e.published_at and e.published_at.startswith("20")
    assert e.canonical_link == url
    assert e.extra_meta["field_sources"]["headline"] == "h1"


def test_prothomalo_known_values() -> None:
    """Compared through normalise(): the page encodes য় as precomposed U+09DF, while this literal
    uses U+09AF U+09BC. Raw equality fails; normalised equality holds."""
    e = extract(*load("bn/prothomalo-2"))
    literal = "‘আব্বু, আব্বু, আমাদের জাহাজে মিসাইল অ্যাটাক হইছে, দোয়া করো’"
    assert e.headline != literal
    assert normalise(e.headline) == normalise(literal)
    assert "য়" in e.headline  # raw page encoding preserved in the stored field
    assert normalise(e.byline) == normalise("মাসুদ মিলাদ")
    assert e.published_at == "2026-09-24T00:21:30+06:00"
    assert normalise(e.body_text).startswith(normalise("অসুস্থ ভাইকে নিয়ে চট্টগ্রাম নগরের এনায়েতবাজারের বাসা থেকে"))


@pytest.mark.parametrize("name", BN)
def test_extraction_is_deterministic(name: str) -> None:
    html, url = load(name)
    a, b = extract(html, url), extract(html, url)
    assert text_hash(a.body_text) == text_hash(b.body_text)
    assert text_hash(a.headline) == text_hash(b.headline)


NFD_BOUNDARY_SHIFT = pytest.mark.xfail(strict=True, reason=(
    "OPEN DECISION: trafilatura's boundary heuristics count codepoints, so on this page NFD input keeps "
    "the kicker/headline lines in the body and NFC input drops them. Hash-path normalisation cannot "
    "fix that; only NFC-normalising the extractor's input can, which conflicts with CLAUDE.md "
    "'body_text stored raw as extracted'."))


@pytest.mark.parametrize("name", ["bn/prothomalo-1", pytest.param("bn/prothomalo-2", marks=NFD_BOUNDARY_SHIFT)])
def test_same_article_reencoded_nfd_gives_same_hashes(name: str) -> None:
    """Real-page version of the phantom-diff test: the outlet re-serialises the identical article in
    decomposed form (CMS migration, different editor). Raw text differs; hashes must not."""
    html, url = load(name)
    nfd_html = unicodedata.normalize("NFD", html.decode("utf-8")).encode("utf-8")
    assert nfd_html != html
    a, b = extract(html, url), extract(nfd_html, url)
    assert a.body_text != b.body_text  # raw kept as extracted, not normalised
    assert text_hash(a.body_text) == text_hash(b.body_text)
    assert text_hash(a.headline) == text_hash(b.headline)
    assert text_hash(a.byline) == text_hash(b.byline)


def test_real_english_article_extracts() -> None:
    e = extract(*load("en/thedailystar-1"))
    assert e.headline and e.headline.startswith("World leaders jostle")
    assert e.body_text and len(e.body_text) > 1000
    # No raw date in the page: falls back to trafilatura's normalised date, and says so.
    assert e.extra_meta["field_sources"]["published_at"] == "trafilatura_normalised"


def test_extractor_version_fits_column() -> None:
    assert len(EXTRACTOR_VERSION) <= 32
