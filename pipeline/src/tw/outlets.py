"""outlets.yaml: load, validate, sync into the `outlet` table, and write discovery results back.

Write-back uses ruamel round-trip mode so hand-written comments and ordering survive.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from sqlalchemy import select
from sqlalchemy.orm import Session

from tw.db.models import Outlet


class OutletConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str
    name: str
    language: Literal["bn", "en"]
    base_url: str
    tier: Literal["bangla_mass", "bangla_other", "english", "online_native", "state_wire", "independent"]
    cms: str | None = None
    rss_urls: list[str] = Field(default_factory=list)
    sitemap_urls: list[str] = Field(default_factory=list)
    rate_limit_seconds: float | None = None  # None = global default
    needs_js: bool = False
    retain_html: Literal["always", "on_change"] = "always"
    active: bool = True
    limitations: list[str] = Field(default_factory=list)
    notes: str | None = None
    discovery: dict[str, Any] | None = None  # yaml-only summary of the last `tw discover`

    @field_validator("base_url")
    @classmethod
    def _base_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("base_url must be absolute http(s)")
        return v.rstrip("/")


def _yaml() -> YAML:
    y = YAML()  # round-trip
    y.indent(mapping=2, sequence=4, offset=2)
    y.width = 4096
    y.preserve_quotes = True
    return y


def load_outlets(path: Path) -> list[OutletConfig]:
    doc = _yaml().load(path.read_text(encoding="utf-8"))
    raw = (doc or {}).get("outlets") or {}
    return [OutletConfig(slug=slug, **dict(fields or {})) for slug, fields in raw.items()]


def _plain_to_yaml(value: Any) -> Any:
    if isinstance(value, dict):
        m = CommentedMap()
        for k, v in value.items():
            m[k] = _plain_to_yaml(v)
        return m
    if isinstance(value, list):
        s = CommentedSeq(_plain_to_yaml(v) for v in value)
        return s
    return value


def write_back(path: Path, slug: str, updates: dict[str, Any]) -> None:
    """Replace the discover-owned fields of one outlet, leaving everything else byte-identical."""
    y = _yaml()
    doc = y.load(path.read_text(encoding="utf-8"))
    entry = doc["outlets"][slug]
    for key, value in updates.items():
        entry[key] = _plain_to_yaml(value)
    OutletConfig(slug=slug, **dict(entry))  # never write back something we could not load
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        y.dump(doc, fh)
    tmp.replace(path)


def sync_outlets(session: Session, configs: list[OutletConfig], default_rate: float) -> dict[str, Outlet]:
    """Upsert config into the DB. Outlets removed from YAML are deactivated, never deleted."""
    existing = {o.slug: o for o in session.scalars(select(Outlet))}
    seen = set()
    for c in configs:
        seen.add(c.slug)
        o = existing.get(c.slug)
        if o is None:
            o = Outlet(slug=c.slug)
            session.add(o)
            existing[c.slug] = o
        o.name = c.name
        o.language = c.language
        o.base_url = c.base_url
        o.cms = c.cms
        o.rss_urls = list(c.rss_urls)
        o.sitemap_urls = list(c.sitemap_urls)
        o.tier = c.tier
        o.rate_limit_seconds = max(c.rate_limit_seconds or default_rate, default_rate)
        o.needs_js = c.needs_js
        o.retain_html = c.retain_html
        o.active = c.active
        o.limitations = list(c.limitations)
    for slug, o in existing.items():
        if slug not in seen:
            o.active = False
    session.flush()
    return existing
