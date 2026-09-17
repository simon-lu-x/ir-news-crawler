import itertools
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

from irnews.middlewares import parse_retry_after
from tests.fixture_site import FixtureSite
from tests.helpers import gaps, run_fixture_crawl

# Keep normal politeness short so the tests measure the backoff, not the delay.
FAST = ["DOWNLOAD_DELAY=0.2", "AUTOTHROTTLE_START_DELAY=0.2"]
TOLERANCE = 0.05


def rate_limited(first_n, headers=None):
    """Responder: the first `first_n` page requests get a 429, the rest succeed."""
    counter = itertools.count(1)

    def respond(path, hit_number):
        if next(counter) <= first_n:
            return 429, headers or {}, "slow down"
        return None

    return respond


def test_retry_after_pauses_the_whole_host():
    with FixtureSite(responder=rate_limited(1, {"Retry-After": "3"})) as site:
        log = run_fixture_crawl(site.base_url, 4, *FAST)

    times = site.times_for("/page/")
    assert len(times) == 5, site.hits  # 4 pages plus 1 retry
    first_429 = times[0]
    # Every later request, to any page on this host, waited out the Retry-After.
    assert min(t - first_429 for t in times[1:]) >= 3 - TOLERANCE, gaps(times)
    assert "backoff/retry_after/127.0.0.1': 1" in log
    assert "fixture/pages_ok': 4" in log


def test_exponential_backoff_without_retry_after():
    with FixtureSite(responder=rate_limited(3)) as site:
        log = run_fixture_crawl(site.base_url, 1, *FAST, "BACKOFF_BASE=1")

    page_gaps = gaps(site.times_for("/page/"))
    assert len(page_gaps) == 3, site.hits
    for attempt, gap in enumerate(page_gaps):
        expected = 1 * 2**attempt  # 1s, 2s, 4s
        assert gap >= expected - TOLERANCE, page_gaps
        assert gap <= expected * 1.2 + 1.0, page_gaps  # jitter plus scheduling slack
    assert "fixture/pages_ok': 1" in log


def test_gives_up_after_max_retries():
    with FixtureSite(responder=rate_limited(99)) as site:
        log = run_fixture_crawl(
            site.base_url, 1, *FAST, "BACKOFF_BASE=0.3", "BACKOFF_MAX_RETRIES=2"
        )

    assert len(site.times_for("/page/")) == 3, site.hits  # first try plus 2 retries
    assert "backoff/gave_up/max_retries/127.0.0.1': 1" in log


def test_gives_up_when_retry_after_is_longer_than_max():
    with FixtureSite(responder=rate_limited(99, {"Retry-After": "3600"})) as site:
        log = run_fixture_crawl(site.base_url, 1, *FAST, "BACKOFF_MAX=60")

    assert len(site.times_for("/page/")) == 1, site.hits
    assert "backoff/gave_up/retry_after_too_long/127.0.0.1': 1" in log


def test_parse_retry_after():
    now = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)
    assert parse_retry_after(b"120") == 120
    assert parse_retry_after(format_datetime(now + timedelta(seconds=90), usegmt=True), now) == 90
    assert parse_retry_after(format_datetime(now - timedelta(seconds=90), usegmt=True), now) == 0
    assert parse_retry_after("soon") is None
    assert parse_retry_after(None) is None
