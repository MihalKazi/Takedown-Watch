"""Bangla normalisation. Phantom diffs from encoding variance would make M2 useless."""

import unicodedata

import pytest

from tw.extract.hashing import text_hash
from tw.extract.normalise import normalise

ZWJ, ZWNJ, VIRAMA = "‍", "‌", "্"

# One sentence, two byte-different encodings that render identically:
#   কো  precomposed U+09CB            vs  U+09C7 U+09BE
#   গৌ  precomposed U+09CC            vs  U+09C7 U+09D7
#   ড়   U+09DC (composition-excluded) vs  U+09A1 U+09BC
#   য়   U+09DF                         vs  U+09AF U+09BC
#   ৎ   U+09CE khanda ta               vs  legacy TA + VIRAMA + ZWJ
COMPOSED = "সরকার কোনো গৌরবের সড়ক নিয়ে উৎসব করবে না।"
DECOMPOSED = (
    "সরকার কোনো গৌরবের সড়ক "
    "নিয়ে উত্‍সব করবে না।"
)


def test_differently_encoded_identical_bangla_hash_equal() -> None:
    """Acceptance criterion: visually identical, differently encoded Bangla -> equal hashes."""
    assert COMPOSED.encode() != DECOMPOSED.encode()
    assert COMPOSED != DECOMPOSED
    assert text_hash(COMPOSED) == text_hash(DECOMPOSED)


def test_nfd_of_whole_text_hashes_equal() -> None:
    assert text_hash(unicodedata.normalize("NFD", COMPOSED)) == text_hash(COMPOSED)


def test_zwj_inside_conjunct_is_preserved() -> None:
    """র‍্যাব (RAB, ra + ZWJ + virama + ya: ya-phala form) renders differently from র্যাব (reph form).
    Stripping the ZWJ would silently equate two different renderings."""
    rab_zwj = "র" + ZWJ + VIRAMA + "যাব"
    rab_reph = "র" + VIRAMA + "যাব"
    assert ZWJ in normalise(rab_zwj)
    assert text_hash(rab_zwj) != text_hash(rab_reph)


def test_zwnj_after_virama_is_preserved() -> None:
    """ক্‌ষ (explicit virama, no conjunct) vs ক্ষ (conjunct): different renderings."""
    explicit = "ক" + VIRAMA + ZWNJ + "ষ"
    conjunct = "ক" + VIRAMA + "ষ"
    assert ZWNJ in normalise(explicit)
    assert text_hash(explicit) != text_hash(conjunct)


def test_joiners_at_word_edges_and_repeats_are_normalised() -> None:
    assert normalise("শব্দ" + ZWNJ + " কথা") == normalise("শব্দ কথা")
    assert normalise(ZWJ + "শব্দ।") == normalise("শব্দ।")
    doubled = "র" + ZWJ + ZWJ + VIRAMA + "য"
    single = "র" + ZWJ + VIRAMA + "য"
    assert normalise(doubled) == normalise(single)


@pytest.mark.parametrize("variant", [
    "ঢাকা শহর",       # no-break space
    "ঢাকা  শহর",           # double space
    "ঢাকা শহর",       # thin space
    "  ঢাকা শহর\t",        # leading/trailing
    "ঢাকা​শহর".replace("​", " "),
    "ঢাকা শ­হর".replace("­", ""),
])
def test_whitespace_variants(variant: str) -> None:
    assert normalise(variant) == "ঢাকা শহর"


def test_invisible_characters_removed() -> None:
    assert normalise("ঢাকা​ শহর﻿") == normalise("ঢাকা শহর")


def test_quotes_and_dashes() -> None:
    assert normalise("“আব্বু” — ‘দোয়া’") == normalise('"আব্বু" - \'দোয়া\'')


def test_blank_lines_and_crlf() -> None:
    assert normalise("প্রথম\r\n\r\n\r\nদ্বিতীয়\n") == "প্রথম\nদ্বিতীয়"


def test_paragraph_breaks_still_matter() -> None:
    assert text_hash("প্রথম\nদ্বিতীয়") != text_hash("প্রথম দ্বিতীয়")


def test_bangla_digits_not_folded() -> None:
    """২০২৬ vs 2026 is a visible change; normalisation must not hide it."""
    assert text_hash("২০২৬ সাল") != text_hash("2026 সাল")


def test_idempotent() -> None:
    once = normalise(DECOMPOSED)
    assert normalise(once) == once


def test_none_and_empty() -> None:
    assert normalise(None) == normalise("") == ""
    assert text_hash(None) == text_hash("")


def test_real_change_is_detected() -> None:
    assert text_hash(COMPOSED) != text_hash(COMPOSED.replace("করবে না", "করবে"))
