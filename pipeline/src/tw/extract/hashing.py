from __future__ import annotations

import hashlib

from tw.extract.normalise import normalise


def text_hash(text: str | None) -> str:
    """sha256 of the normalised text. None and "" hash identically; the raw column keeps the difference."""
    return hashlib.sha256(normalise(text).encode("utf-8")).hexdigest()
