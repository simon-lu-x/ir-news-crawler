from tests.fixture_site import FixtureSite
from tests.helpers import gaps, run_fixture_crawl

CRAWL_DELAY = 3


def test_requests_to_one_host_are_at_least_crawl_delay_apart():
    robots = f"User-agent: *\nCrawl-delay: {CRAWL_DELAY}\nAllow: /\n"
    with FixtureSite(robots_txt=robots) as site:
        log = run_fixture_crawl(site.base_url, 5)

    page_gaps = gaps(site.times_for("/page/"))
    assert len(page_gaps) == 4, site.hits
    # Small tolerance for timer resolution only. Jitter would give gaps down to 1.5s.
    assert min(page_gaps) >= CRAWL_DELAY - 0.05, page_gaps
    assert f"robotstxt/crawl_delay/127.0.0.1': {float(CRAWL_DELAY)}" in log
