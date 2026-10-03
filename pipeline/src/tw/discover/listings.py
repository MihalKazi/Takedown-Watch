"""Parse RSS 2.0 / RSS 1.0 / Atom feeds and XML sitemaps (urlset, sitemapindex, Google News).

Namespace-agnostic: matches on local names, because outlets emit every namespace variant imaginable.
Returns None for anything that is not one of these documents (HTML error pages, JSON, empty bodies).
"""

from __future__ import annotations

import gzip
from dataclasses import dataclass, field
from typing import Literal

from lxml import etree

ListingKind = Literal["rss", "atom", "sitemap", "news_sitemap", "sitemap_index"]

_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True, recover=False)


@dataclass
class ListingItem:
    url: str
    title: str | None = None
    date: str | None = None  # raw string as published: pubDate, updated, lastmod, news:publication_date


@dataclass
class ParsedListing:
    kind: ListingKind
    items: list[ListingItem] = field(default_factory=list)


def _local(el: etree._Element) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def _child(el: etree._Element, name: str) -> etree._Element | None:
    for c in el:
        if _local(c) == name:
            return c
    return None


def _children(el: etree._Element, name: str) -> list[etree._Element]:
    return [c for c in el if _local(c) == name]


def _text(el: etree._Element | None) -> str | None:
    if el is None:
        return None
    t = "".join(el.itertext()).strip()
    return t or None


def _first_text(el: etree._Element, *names: str) -> str | None:
    for n in names:
        t = _text(_child(el, n))
        if t:
            return t
    return None


def _rss_items(items: list[etree._Element]) -> list[ListingItem]:
    out = []
    for it in items:
        link = _text(_child(it, "link"))
        if not link:
            guid = _child(it, "guid")
            if guid is not None and guid.get("isPermaLink", "true").lower() == "true":
                link = _text(guid)
        if not link:
            link = it.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about")
        if link:
            out.append(ListingItem(url=link, title=_text(_child(it, "title")),
                                   date=_first_text(it, "pubDate", "date", "published", "updated")))
    return out


def _atom_items(root: etree._Element) -> list[ListingItem]:
    out = []
    for entry in _children(root, "entry"):
        href = None
        for link in _children(entry, "link"):
            if link.get("rel", "alternate") == "alternate" and link.get("href"):
                href = link.get("href")
                break
        if href:
            out.append(ListingItem(url=href, title=_text(_child(entry, "title")),
                                   date=_first_text(entry, "published", "updated")))
    return out


def _sitemap_items(root: etree._Element) -> tuple[list[ListingItem], bool]:
    out, is_news = [], False
    for u in _children(root, "url"):
        loc = _text(_child(u, "loc"))
        if not loc:
            continue
        news = _child(u, "news")
        title = date = None
        if news is not None:
            is_news = True
            title = _text(_child(news, "title"))
            date = _text(_child(news, "publication_date"))
        out.append(ListingItem(url=loc, title=title, date=date or _text(_child(u, "lastmod"))))
    return out, is_news


def parse_listing(content: bytes) -> ParsedListing | None:
    if content[:2] == b"\x1f\x8b":
        try:
            content = gzip.decompress(content)
        except OSError:
            return None
    content = content.lstrip(b"\xef\xbb\xbf \t\r\n")
    if not content.startswith(b"<"):
        return None
    try:
        root = etree.fromstring(content, _PARSER)
    except etree.XMLSyntaxError:
        return None
    if root is None:
        return None
    name = _local(root)
    if name == "rss":
        channel = _child(root, "channel")
        return ParsedListing("rss", _rss_items(_children(channel, "item") if channel is not None else []))
    if name == "RDF":
        return ParsedListing("rss", _rss_items(_children(root, "item")))
    if name == "feed":
        return ParsedListing("atom", _atom_items(root))
    if name == "urlset":
        items, is_news = _sitemap_items(root)
        return ParsedListing("news_sitemap" if is_news else "sitemap", items)
    if name == "sitemapindex":
        return ParsedListing("sitemap_index", [
            ListingItem(url=loc, date=_text(_child(s, "lastmod")))
            for s in _children(root, "sitemap")
            if (loc := _text(_child(s, "loc")))
        ])
    return None
