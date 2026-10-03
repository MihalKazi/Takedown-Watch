"""URL canonicalisation. Conservative: only changes that cannot point to a different document."""

from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = {
    "fbclid", "gclid", "dclid", "gbraid", "wbraid", "msclkid", "yclid", "twclid", "igshid",
    "mc_cid", "mc_eid", "_ga", "_gl", "ref_src", "ocid", "cmpid", "s_cid",
}
TRACKING_PREFIXES = ("utm_", "pk_", "mtm_", "hsa_")


def canonicalise(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower().rstrip(".")
    port = parts.port
    netloc = host if port is None or (scheme, port) in {("http", 80), ("https", 443)} else f"{host}:{port}"
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS and not k.lower().startswith(TRACKING_PREFIXES)
    ]
    query.sort()
    return urlunsplit((scheme, netloc, parts.path or "/", urlencode(query, doseq=True), ""))


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()
