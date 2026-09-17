import sqlite3

from irnews.spiders.press_detail import PARSER_VERSION
from tests.fixture_ir_site import IRSite
from tests.helpers import run_press_crawl, stat

FAST = ("DOWNLOAD_DELAY=0", "AUTOTHROTTLE_ENABLED=False")


def crawl(site, db, *args):
    return run_press_crawl(f"T={site.listing_url}", db, "max_pages=10", *args, settings=FAST)


def test_incremental_crawl(tmp_path):
    db = tmp_path / "irnews.db"
    # 9 releases over 3 pages: [9 8 7] [6 5 4] [3 2 1]
    with IRSite(ids=range(9, 0, -1)) as site:
        # First run: empty database, so everything is fetched.
        log = crawl(site, db)
        assert site.detail_hits() == list(range(1, 10))
        assert stat(log, "store/inserted/T") == 9

        # Two new releases appear on top: [11 10 9] [8 7 6] [5 4 3] [2 1]
        site.ids = [11, 10] + site.ids
        site.reset_hits()
        log = crawl(site, db)
        assert site.detail_hits() == [10, 11]
        # Page 1 had new items, page 2 had none, so paging stopped at page 2.
        assert len(site.listing_hits()) == 2
        assert stat(log, "incremental/stopped_at_page/T") == 2
        assert stat(log, "store/inserted/T") == 2

        # Nothing new: one listing page, no detail pages.
        site.reset_hits()
        log = crawl(site, db)
        assert site.detail_hits() == []
        assert len(site.listing_hits()) == 1

        # full=1 ignores what is stored.
        site.reset_hits()
        log = crawl(site, db, "full=1")
        assert site.detail_hits() == list(range(1, 12))
        assert stat(log, "store/updated/T") == 11

    with sqlite3.connect(db) as conn:
        assert conn.execute("select count(*) from press_releases").fetchone()[0] == 11


def test_rows_from_an_older_parser_are_fetched_again(tmp_path):
    db = tmp_path / "irnews.db"
    with IRSite(ids=range(6, 0, -1)) as site:
        crawl(site, db)

        # Pretend releases 5 and 2 were saved by an older parser.
        with sqlite3.connect(db) as conn:
            conn.execute(
                "update press_releases set parser_version = ? where source_id in ('5', '2')",
                (PARSER_VERSION - 1,),
            )

        site.reset_hits()
        log = crawl(site, db)
        assert site.detail_hits() == [2, 5]
        assert stat(log, "store/updated/T") == 2

    with sqlite3.connect(db) as conn:
        versions = {v for (v,) in conn.execute("select parser_version from press_releases")}
    assert versions == {PARSER_VERSION}


def test_database_from_before_parser_version_is_migrated(tmp_path):
    db = tmp_path / "irnews.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "create table press_releases (url text primary key, ticker text not null,"
            " source_id text, title text not null, published_at text not null,"
            " body_text text not null, content_hash text not null,"
            " first_seen_at text not null, last_seen_at text not null)"
        )
        conn.execute(
            "insert into press_releases values ('u', 'T', '3', 't', 'd', 'b', 'h', 'x', 'x')"
        )

    with IRSite(ids=[3, 2, 1]) as site:
        crawl(site, db)
        # The old row has no parser version, so release 3 is fetched like the others.
        assert site.detail_hits() == [1, 2, 3]
