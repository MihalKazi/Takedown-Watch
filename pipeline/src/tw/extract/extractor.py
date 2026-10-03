"""Article extraction: trafilatura for the body, targeted lxml parsing for metadata.

All metadata is kept as the raw strings the page carries: no date parsing, no author cleanup.
Every candidate source for each field goes into `extra_meta`, so a later extractor can revisit the
choice without refetching. EXTRACTOR_VERSION changes whenever this file or the libraries change
output, so M2 can tell our upgrades from outlets' edits.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import lxml.etree
import trafilatura
from lxml import html as lxml_html

_TW_EXTRACTOR_REV = "1"
EXTRACTOR_VERSION = f"tw{_TW_EXTRACTOR_REV}+traf{trafilatura.__version__}+lxml{lxml.etree.__version__}"

ARTICLE_TYPES = {"NewsArticle", "Article", "ReportageNewsArticle", "AnalysisNewsArticle",
                 "OpinionNewsArticle", "BlogPosting", "LiveBlogPosting", "BackgroundNewsArticle"}


@dataclass
class Extraction:
    headline: str | None
    byline: str | None
    published_at: str | None
    modified_at: str | None
    body_text: str | None
    canonical_link: str | None
    extra_meta: dict[str, Any] = field(default_factory=dict)


def _meta(doc: lxml_html.HtmlElement, *keys: str) -> str | None:
    for k in keys:
        for attr in ("property", "name", "itemprop"):
            vals = doc.xpath(f"//meta[@{attr}=$k]/@content", k=k)
            if vals and str(vals[0]).strip():
                return str(vals[0]).strip()
    return None


def _jsonld_articles(doc: lxml_html.HtmlElement) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for n in node:
                walk(n)
        elif isinstance(node, dict):
            t = node.get("@type")
            types = set(t) if isinstance(t, list) else {t}
            if types & ARTICLE_TYPES:
                found.append(node)
            for key in ("@graph", "mainEntity", "itemListElement"):
                if key in node:
                    walk(node[key])

    for script in doc.xpath("//script[@type='application/ld+json']"):
        try:
            walk(json.loads(script.text_content(), strict=False))
        except (ValueError, TypeError):
            continue
    return found


def _names(author: Any) -> list[str]:
    if isinstance(author, str):
        return [author]
    if isinstance(author, dict):
        n = author.get("name")
        return [n] if isinstance(n, str) else []
    if isinstance(author, list):
        return [x for a in author for x in _names(a)]
    return []


def extract(html_bytes: bytes, url: str) -> Extraction:
    doc = lxml_html.fromstring(html_bytes)

    canonical = None
    for link in doc.iter("link"):
        if "canonical" in (link.get("rel") or "").lower().split() and link.get("href"):
            canonical = link.get("href").strip()
            break

    h1s = [" ".join(h.text_content().split()) for h in doc.xpath("//h1")]
    ld = _jsonld_articles(doc)
    ld0 = ld[0] if ld else {}
    ld_authors = _names(ld0.get("author"))

    meta = {
        "h1": h1s[:3],
        "og_title": _meta(doc, "og:title"),
        "twitter_title": _meta(doc, "twitter:title"),
        "title_tag": next((t.text_content().strip() for t in doc.xpath("//head/title")), None),
        "meta_author": _meta(doc, "author", "article:author", "dc.creator"),
        "meta_published": _meta(doc, "article:published_time", "datePublished", "pubdate",
                                "publish-date", "dc.date"),
        "meta_modified": _meta(doc, "article:modified_time", "og:updated_time", "dateModified"),
        "jsonld_type": ld0.get("@type"),
        "jsonld_headline": ld0.get("headline") if isinstance(ld0.get("headline"), str) else None,
        "jsonld_authors": ld_authors,
        "jsonld_published": ld0.get("datePublished") if isinstance(ld0.get("datePublished"), str) else None,
        "jsonld_modified": ld0.get("dateModified") if isinstance(ld0.get("dateModified"), str) else None,
        "html_lang": doc.get("lang"),
    }

    traf = trafilatura.bare_extraction(
        html_bytes, url=url, with_metadata=True, include_comments=False, include_tables=True,
        include_images=False, include_links=False, deduplicate=False, favor_precision=False,
    )
    tdoc = traf.as_dict() if traf is not None and hasattr(traf, "as_dict") else (traf or {})
    meta["trafilatura"] = {k: tdoc.get(k) for k in
                           ("title", "author", "date", "sitename", "categories", "tags", "language",
                            "description", "pagetype")}

    sources: dict[str, str | None] = {}

    def pick(name: str, *candidates: tuple[str, str | None]) -> str | None:
        for src, v in candidates:
            if v and v.strip():
                sources[name] = src
                return v.strip()
        sources[name] = None
        return None

    # trafilatura's date is normalised (YYYY-MM-DD), not a raw page string: used only as last resort,
    # and field_sources says so.
    result = Extraction(
        headline=pick("headline", ("h1", h1s[0] if h1s else None), ("jsonld", meta["jsonld_headline"]),
                      ("og:title", meta["og_title"]), ("trafilatura", tdoc.get("title"))),
        byline=pick("byline", ("jsonld", ", ".join(ld_authors) if ld_authors else None),
                    ("meta", meta["meta_author"]), ("trafilatura", tdoc.get("author"))),
        published_at=pick("published_at", ("jsonld", meta["jsonld_published"]), ("meta", meta["meta_published"]),
                          ("trafilatura_normalised", tdoc.get("date"))),
        modified_at=pick("modified_at", ("jsonld", meta["jsonld_modified"]), ("meta", meta["meta_modified"])),
        body_text=tdoc.get("text") or None,
        canonical_link=canonical,
        extra_meta=meta,
    )
    meta["field_sources"] = sources
    return result
