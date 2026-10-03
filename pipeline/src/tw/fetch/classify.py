"""Map a raw HTTP exchange to a fetch outcome. Outcomes are observations, recorded on every fetch_attempt."""

from __future__ import annotations

from enum import StrEnum

import httpx


class Outcome(StrEnum):
    OK = "ok"  # 2xx
    HTTP_ERROR = "http_error"  # any other final status (404, 410, 403, 5xx ...)
    CF_CHALLENGE = "cf_challenge"  # Cloudflare interstitial: not a failure, not content
    RATE_LIMITED = "rate_limited"  # 429
    TIMEOUT = "timeout"
    CONN_ERROR = "conn_error"  # DNS, TLS, refused, reset, too many redirects
    TOO_LARGE = "too_large"  # body exceeded http_max_bytes
    ROBOTS_BLOCKED = "robots_blocked"  # not requested: robots.txt disallows it (no HTTP exchange)


RETRYABLE = {Outcome.TIMEOUT, Outcome.CONN_ERROR, Outcome.RATE_LIMITED}

_CF_BODY_MARKERS = (
    b"challenge-platform",
    b"cf-chl-",
    b"cf_chl_opt",
    b"<title>Just a moment...</title>",
    b"Attention Required! | Cloudflare",
)


def is_cf_challenge(status: int, headers: httpx.Headers, body_head: bytes) -> bool:
    if headers.get("cf-mitigated", "").lower() == "challenge":
        return True
    if status in (403, 429, 503) and "cloudflare" in headers.get("server", "").lower():
        return any(m in body_head for m in _CF_BODY_MARKERS)
    return False


def classify(status: int, headers: httpx.Headers, body: bytes) -> Outcome:
    if is_cf_challenge(status, headers, body[:32_768]):
        return Outcome.CF_CHALLENGE
    if status == 429:
        return Outcome.RATE_LIMITED
    if 200 <= status < 300:
        return Outcome.OK
    return Outcome.HTTP_ERROR


def is_retryable(outcome: Outcome, status: int | None) -> bool:
    """Retry transient failures only. A 404/410 is never retried; neither is a CF challenge."""
    if outcome in RETRYABLE:
        return True
    return outcome is Outcome.HTTP_ERROR and status is not None and status >= 500
