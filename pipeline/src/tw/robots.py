"""robots.txt fetch and interpretation per RFC 9309. Used by discover and crawl."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

from tw.fetch.classify import Outcome
from tw.fetch.client import Fetcher, FetchResult


@dataclass
class Robots:
    parser: RobotFileParser | None  # None = no restrictions
    token: str
    info: dict = field(default_factory=dict)
    limitation: str | None = None

    def allowed(self, url: str) -> bool:
        return self.parser is None or self.parser.can_fetch(self.token, url)

    @property
    def disallow_all(self) -> bool:
        return self.parser is not None and self.parser.disallow_all


async def fetch_robots(fetcher: Fetcher, base_url: str, token: str,
                       record: Callable[[str, FetchResult], object]) -> Robots:
    url = urljoin(base_url, "/robots.txt")
    res = await fetcher.get(url)
    record("robots", res)
    info: dict = {"url": url, "status": res.status, "outcome": str(res.outcome), "sitemaps": []}
    rp = RobotFileParser()
    if res.ok:
        rp.parse(res.text().splitlines())
        info["sitemaps"] = list(rp.site_maps() or [])
        robots = Robots(rp, token, info)
    elif res.outcome is Outcome.HTTP_ERROR and res.status is not None and 400 <= res.status < 500:
        # RFC 9309 §2.3.1.3: 4xx means no restrictions.
        info["note"] = "no robots.txt: unrestricted"
        robots = Robots(None, token, info)
    else:
        # RFC 9309 §2.3.1.4: unreachable robots.txt means assume complete disallow.
        rp.disallow_all = True
        robots = Robots(rp, token, info, limitation=f"robots_unavailable_{res.outcome}")
    info["disallows_homepage"] = not robots.allowed(urljoin(base_url, "/"))
    return robots
