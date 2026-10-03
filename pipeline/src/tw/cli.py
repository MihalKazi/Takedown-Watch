from __future__ import annotations

import asyncio
import sys
from typing import Annotated

import typer

from tw.config import PIPELINE_ROOT, get_settings
from tw.log import configure_logging

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Takedown Watch capture pipeline.")


@app.callback()
def _main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")  # Windows consoles default to a legacy codepage
    s = get_settings()
    configure_logging(s.log_level, s.log_format)


@app.command()
def initdb() -> None:
    """Create or upgrade the database schema (alembic upgrade head)."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(PIPELINE_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PIPELINE_ROOT / "migrations"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    typer.echo(f"schema at head: {get_settings().database_url}")


@app.command()
def discover(
    outlet: Annotated[list[str] | None, typer.Option("--outlet", "-o", help="Outlet slug; repeatable.")] = None,
    write: Annotated[bool, typer.Option(help="Write confirmed feeds back to outlets.yaml.")] = True,
) -> None:
    """Probe and verify RSS feeds and sitemaps for configured outlets."""
    from tw.db.session import session_scope
    from tw.discover.report import render
    from tw.discover.run import discover as run_discover

    settings = get_settings()
    with session_scope() as session:
        results = asyncio.run(run_discover(settings, session, outlet, write=write))
    typer.echo(render(results))


@app.command()
def crawl(
    outlet: Annotated[list[str] | None, typer.Option("--outlet", "-o", help="Outlet slug; repeatable.")] = None,
    max_articles: Annotated[int | None, typer.Option(help="Cap article fetches per outlet this run.")] = None,
) -> None:
    """One discovery + capture pass. Enqueues archival; does not perform it."""
    from tw.crawl import crawl as run_crawl
    from tw.db.session import get_engine

    runs = asyncio.run(run_crawl(get_settings(), get_engine(), outlet, max_articles))
    for r in runs:
        i = r.ingest
        typer.echo(f"{r.slug:17} listings ok={i.listings_ok} failed={len(i.listings_failed)}  "
                   f"entries={i.entries_seen} new={i.new_articles} known={i.known_articles} "
                   f"outside_window={i.outside_window} off_site={i.off_site}  "
                   f"captures: {dict(r.captures) or '-'}")
        for f in i.listings_failed:
            typer.echo(f"{'':17} listing failed: {f}")


@app.command()
def archive(
    limit: Annotated[int | None, typer.Option(help="Max new submissions this run.")] = None,
) -> None:
    """Drain the archival queue to Internet Archive Save Page Now."""
    from tw.archive.run import coverage, drain
    from tw.db.session import get_engine

    engine = get_engine()
    counts = asyncio.run(drain(get_settings(), engine, limit))
    total, ok = coverage(engine)
    typer.echo(f"this run: {dict(counts) or 'nothing queued'}")
    typer.echo(f"coverage: {ok}/{total} snapshots archived" + (f" ({ok / total:.1%})" if total else ""))


@app.command()
def stats() -> None:
    """Coverage: articles, snapshots, archive rate, extraction health."""
    from tw.db.session import get_engine
    from tw.stats import collect, render

    typer.echo(render(collect(get_engine())))


@app.command()
def export() -> None:
    """Write the open dataset (data/v1/*.json) that the public site is built from."""
    from tw.db.session import get_engine
    from tw.export import build, write

    settings = get_settings()
    out = write(build(get_engine(), settings), settings.data_dir)
    typer.echo(f"wrote {out}")


if __name__ == "__main__":
    app()
