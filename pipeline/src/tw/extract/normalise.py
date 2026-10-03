"""Text normalisation for the hashing and diffing path ONLY. Stored text is always raw.

Goal: identical rendered text -> identical string. Bangla has several encodings that render the
same; without this, M2 would report phantom edits at scale. Every rule here must be a change that
cannot alter what a reader sees. Bump NORMALISER_VERSION whenever a rule changes: hashes from
different versions are not comparable, and snapshot.normaliser_version records which one applied.
"""

from __future__ import annotations

import re
import unicodedata

NORMALISER_VERSION = "1"

ZWNJ = "‌"
ZWJ = "‍"

# Invisible and without meaning in running text. (ZWJ/ZWNJ are NOT here: they shape conjuncts.)
_INVISIBLE = dict.fromkeys(map(ord, "​⁠﻿­᠎"), None)

_QUOTES = str.maketrans({
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"', "«": '"', "»": '"',
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'", "‹": "'", "›": "'",
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-",
})

# Pre-Unicode-4.1 khanda ta: TA + VIRAMA + ZWJ renders as U+09CE KHANDA TA.
_KHANDA_TA_LEGACY = "ত্‍"
_KHANDA_TA = "ৎ"

# ZWJ/ZWNJ touching whitespace, punctuation or a string edge join nothing: no rendering effect.
# Runs of the same joiner render identically to one.
_JOINER_RUN = re.compile(f"([{ZWJ}{ZWNJ}])\\1+")


def _is_boundary(ch: str | None) -> bool:
    # Explicit categories, not regex \W: \W matches Bangla virama and vowel signs, and a joiner
    # after a virama is exactly the one that matters.
    return ch is None or ch.isspace() or unicodedata.category(ch)[0] in "PZ"


def _drop_edge_joiners(t: str) -> str:
    out: list[str] = []
    n = len(t)
    for i, ch in enumerate(t):
        if ch in (ZWJ, ZWNJ):
            prev = out[-1] if out else None
            nxt = t[i + 1] if i + 1 < n else None
            if _is_boundary(prev) or _is_boundary(nxt):
                continue
        out.append(ch)
    return "".join(out)

_HSPACE = re.compile(r"[^\S\n]+")  # any whitespace except newline, incl. NBSP and U+2000-200A


def normalise(text: str | None) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFC", text)
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = t.translate(_INVISIBLE)
    t = t.replace(_KHANDA_TA_LEGACY, _KHANDA_TA)
    t = _JOINER_RUN.sub(r"\1", t)
    t = _drop_edge_joiners(t)
    t = t.translate(_QUOTES)
    t = _HSPACE.sub(" ", t)
    lines = (line.strip() for line in t.split("\n"))
    t = "\n".join(line for line in lines if line)
    return unicodedata.normalize("NFC", t)
