"""Listing parser. Titles are Bangla on purpose: the parser must round-trip them byte-exact."""

import gzip

from tw.discover.listings import parse_listing

BN_TITLE = "ঢাকায় বৃষ্টিতে জলাবদ্ধতা, দুর্ভোগে নগরবাসী"

RSS = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/"><channel><title>t</title>
<item><title>{BN_TITLE}</title><link>https://www.prothomalo.com/bangladesh/abc123</link>
<pubDate>Wed, 23 Sep 2026 10:00:00 +0600</pubDate></item>
<item><title>no link but permalink guid</title><guid isPermaLink="true">https://www.prothomalo.com/x</guid></item>
<item><title>non-permalink guid is not a url</title><guid isPermaLink="false">12345</guid></item>
</channel></rss>""".encode()

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>t</title>
<entry><title>a</title><link rel="alternate" href="https://netra.news/2026/a"/><updated>2026-09-23T04:00:00Z</updated></entry>
<entry><title>b</title><link rel="self" href="https://netra.news/feed/b"/></entry>
</feed>"""

NEWS_SITEMAP = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
<url><loc>https://www.thedailystar.net/news/a-1</loc>
<news:news><news:publication><news:name>The Daily Star</news:name><news:language>en</news:language></news:publication>
<news:publication_date>2026-09-23T10:00:00+06:00</news:publication_date><news:title>{BN_TITLE}</news:title></news:news></url>
</urlset>""".encode()

SITEMAP = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://bdnews24.com/a</loc><lastmod>2026-09-20</lastmod></url></urlset>"""

INDEX = b"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://bdnews24.com/sitemap-news.xml</loc></sitemap>
<sitemap><loc>https://bdnews24.com/sitemap-2026-09.xml</loc><lastmod>2026-09-23</lastmod></sitemap>
</sitemapindex>"""


def test_rss_items_and_bangla_title_roundtrip() -> None:
    p = parse_listing(RSS)
    assert p is not None and p.kind == "rss"
    assert [i.url for i in p.items] == ["https://www.prothomalo.com/bangladesh/abc123", "https://www.prothomalo.com/x"]
    assert p.items[0].title == BN_TITLE
    assert p.items[0].date == "Wed, 23 Sep 2026 10:00:00 +0600"


def test_atom_uses_alternate_links_only() -> None:
    p = parse_listing(ATOM)
    assert p is not None and p.kind == "atom"
    assert [i.url for i in p.items] == ["https://netra.news/2026/a"]


def test_news_sitemap_detected_by_namespace() -> None:
    p = parse_listing(NEWS_SITEMAP)
    assert p is not None and p.kind == "news_sitemap"
    assert p.items[0].title == BN_TITLE
    assert p.items[0].date == "2026-09-23T10:00:00+06:00"


def test_plain_sitemap_and_index() -> None:
    s = parse_listing(SITEMAP)
    assert s is not None and s.kind == "sitemap" and s.items[0].date == "2026-09-20"
    i = parse_listing(INDEX)
    assert i is not None and i.kind == "sitemap_index" and len(i.items) == 2


def test_gzipped_sitemap() -> None:
    p = parse_listing(gzip.compress(SITEMAP))
    assert p is not None and p.kind == "sitemap"


def test_bom_and_leading_whitespace_tolerated() -> None:
    assert parse_listing(b"\xef\xbb\xbf\n  " + SITEMAP) is not None


def test_html_and_junk_rejected() -> None:
    assert parse_listing(b"<!doctype html><html><body>404</body></html>") is None
    assert parse_listing(b'<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"/>') is None
    assert parse_listing(b'{"json": true}') is None
    assert parse_listing(b"") is None


def test_external_entities_not_resolved() -> None:
    xxe = b"""<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>
<rss><channel><item><title>&x;</title><link>https://a.example/1</link></item></channel></rss>"""
    p = parse_listing(xxe)
    assert p is None or all("root:" not in (i.title or "") for i in p.items)
