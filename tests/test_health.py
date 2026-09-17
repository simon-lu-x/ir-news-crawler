import sqlite3

from scrapy.http import HtmlResponse

from irnews.spiders.press_detail import extract_body, text_coverage
from tests.fixture_ir_site import IRSite
from tests.helpers import run_press_crawl

FAST = ("DOWNLOAD_DELAY=0", "AUTOTHROTTLE_ENABLED=False")


def crawl(site, db, *args):
    return run_press_crawl(f"T={site.listing_url}", db, "max_pages=10", *args, settings=FAST)


def last_run(db):
    with sqlite3.connect(db) as conn:
        return conn.execute(
            "select status, failed_checks from crawl_runs order by rowid desc limit 1"
        ).fetchone()


def test_healthy_run_is_ok_even_with_nothing_new(tmp_path):
    db = tmp_path / "irnews.db"
    with IRSite(ids=range(6, 0, -1)) as site:
        log = crawl(site, db)
        assert last_run(db) == ("ok", "")
        assert "'health/status/T': 'ok'" in log

        # Nothing new was published. Zero items is normal, not a failure.
        log = crawl(site, db)
        assert "'item_scraped_count'" not in log
        assert last_run(db) == ("ok", "")


def test_blocked_listing(tmp_path):
    db = tmp_path / "irnews.db"
    with IRSite(ids=range(3, 0, -1)) as site:
        site.listing_status = 403
        log = crawl(site, db)
    assert "'finish_reason': 'finished'" in log  # nothing crashed
    assert last_run(db) == ("failed", "listing_not_reached")
    assert "HEALTH FAILED for T: listing_not_reached" in log


def test_listing_selector_stops_matching(tmp_path):
    db = tmp_path / "irnews.db"
    with IRSite(ids=range(3, 0, -1), layout="intel") as site:
        crawl(site, db, "layout=amd")
    assert last_run(db) == ("failed", "listing_empty")


def test_fewer_links_per_page_than_last_run(tmp_path):
    db = tmp_path / "irnews.db"
    with IRSite(ids=range(9, 0, -1)) as site:
        crawl(site, db)
        assert last_run(db) == ("ok", "")

        # The template changed so only one release per page still matches.
        site.per_page = 1
        crawl(site, db, "full=1", "max_pages=3")
    assert last_run(db) == ("failed", "links_per_page_dropped")


def test_detail_pages_fail_validation(tmp_path):
    db = tmp_path / "irnews.db"
    with IRSite(ids=range(3, 0, -1)) as site:
        site.detail_title = False
        crawl(site, db)
    assert last_run(db) == ("failed", "high_drop_rate")


def test_coverage_catches_the_p_only_parser():
    with IRSite(ids=[1]) as site:
        html = site._detail("1")
    article = HtmlResponse("http://x", body=html.encode(), encoding="utf-8").css(
        "article.full-news-article"
    )
    p_only = " ".join(article.xpath("./p//text()").getall())

    assert text_coverage(extract_body(article, frozenset()), article, frozenset()) == 1.0
    assert text_coverage(p_only, article, frozenset()) < 0.8
