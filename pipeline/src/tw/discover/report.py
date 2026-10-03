"""Plain-text discover report for the terminal."""

from __future__ import annotations

from tw.discover.probe import DiscoveryResult


def render(results: list[DiscoveryResult]) -> str:
    out: list[str] = []
    for r in results:
        h = r.homepage
        out.append(f"== {r.slug}")
        out.append(f"   homepage  {h.get('status')} {h.get('outcome', h.get('skipped'))} -> {h.get('final_url')}"
                   f"  lang={h.get('html_lang')}  cms={r.detected_cms}")
        rb = r.robots
        out.append(f"   robots    {rb.get('status')} {rb.get('outcome')}  sitemaps declared={len(rb.get('sitemaps', []))}"
                   f"  disallows_homepage={rb.get('disallows_homepage')}")
        for c in r.candidates:
            mark = "+" if c.selected else " "
            detail = f"{c.kind or '-'} n={c.entries}" if c.kind else f"{c.outcome or '-'} {c.status or ''}".strip()
            newest = f" newest={c.newest[:16]}" if c.newest else ""
            share = f" on-site={c.on_site_share:.0%}" if c.on_site_share is not None else ""
            out.append(f"   {mark} [{c.source:<13}] {c.final_url or c.url}")
            out.append(f"        {detail}{share}{newest}{'  — ' + c.reason if c.reason else ''}")
        out.append(f"   RSS       {r.rss_urls or 'none'}")
        out.append(f"   sitemaps  {r.sitemap_urls or 'none'}")
        out.append(f"   limits    {r.limitations or 'none'}")
        out.append("")
    return "\n".join(out)
