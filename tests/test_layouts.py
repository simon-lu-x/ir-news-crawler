import sqlite3

from tests.fixture_ir_site import IRSite
from tests.helpers import run_press_crawl, stat

FAST = ("DOWNLOAD_DELAY=0", "AUTOTHROTTLE_ENABLED=False")


def test_intel_layout_takes_one_link_per_release_and_skips_page_furniture(tmp_path):
    db = tmp_path / "irnews.db"
    with IRSite(ids=range(6, 0, -1), layout="intel") as site:
        log = run_press_crawl(
            f"T={site.listing_url}", db, "max_pages=5", "layout=intel", settings=FAST
        )
        assert site.detail_hits() == list(range(1, 7))
    assert stat(log, "store/inserted/T") == 6
    # Each release is linked three times on the listing. Scrapy's dupefilter would
    # still fetch it once, so detail_hits alone cannot tell whether the selector
    # picks one link per release. Filtered duplicates can.
    assert stat(log, "dupefilter/filtered") == 0

    with sqlite3.connect(db) as conn:
        bodies = [b for (b,) in conn.execute("select body_text from press_releases")]
    assert len(bodies) == 6
    for body in bodies:
        assert body.startswith("This is a press release paragraph")
        assert "Related Documents" not in body
        assert "Released Sep" not in body


def test_wrong_layout_finds_nothing_and_says_so(tmp_path):
    # Selectors that do not match the page do not raise. The only sign is a stat.
    db = tmp_path / "irnews.db"
    with IRSite(ids=range(3, 0, -1), layout="intel") as site:
        log = run_press_crawl(
            f"T={site.listing_url}", db, "max_pages=5", "layout=amd", settings=FAST
        )
        assert site.detail_hits() == []
    assert "'finish_reason': 'finished'" in log
    assert stat(log, "item_scraped_count") == 0
    assert stat(log, "listing/empty/T") == 1
