import logging
import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from scrapy import signals

logger = logging.getLogger(__name__)


def parse_retry_after(value, now=None):
    """Return seconds to wait from a Retry-After header, or None if unusable.

    The header is either a number of seconds or an HTTP date.
    """
    if not value:
        return None
    text = value.decode("latin-1") if isinstance(value, bytes) else str(value)
    text = text.strip()
    if text.isdigit():
        return float(text)
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return max(0.0, (when - now).total_seconds())


class RateLimitBackoffMiddleware:
    """Back off when a host says we are going too fast (429, or 503).

    Scrapy's RetryMiddleware puts the request straight back in the queue. It does
    not wait and does not read Retry-After. This middleware does three things
    differently:

    1. It pauses the whole host, not just the one request. A 429 is about our
       rate to that host, so other requests to it should wait too.
    2. It waits exactly as long as Retry-After says. With no header it waits
       BACKOFF_BASE * 2^attempt seconds, plus up to 20% random jitter.
    3. If Retry-After is longer than BACKOFF_MAX, or retries run out, it gives
       up on the request instead of retrying sooner than asked.

    Where the pause happens matters. A first version paused in process_request.
    That was too late: Scrapy had already moved the other requests for the host
    past the middleware and into the host's download slot queue, so they went out
    0.2 seconds after the 429. The pause now happens in the response_downloaded
    signal. Scrapy sends it before the slot picks its next request, which is the
    same hook AutoThrottle uses.

    429 and 503 must be removed from RETRY_HTTP_CODES, or both middlewares retry.
    """

    CODES = (429, 503)

    def __init__(self, crawler):
        self.crawler = crawler
        self.stats = crawler.stats
        settings = crawler.settings
        self.base = settings.getfloat("BACKOFF_BASE", 5)
        self.max_wait = settings.getfloat("BACKOFF_MAX", 300)
        self.max_retries = settings.getint("BACKOFF_MAX_RETRIES", 5)
        crawler.signals.connect(self._response_downloaded, signal=signals.response_downloaded)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def _response_downloaded(self, response, request, spider):
        if response.status not in self.CODES or request.url.endswith("/robots.txt"):
            return
        key = request.meta.get("download_slot")
        attempt = request.meta.get("backoff_attempt", 0)
        retry_after = parse_retry_after(response.headers.get("Retry-After"))

        if attempt >= self.max_retries:
            request.meta["backoff_decision"] = ("give_up", "max_retries")
            return
        if retry_after is not None and retry_after > self.max_wait:
            request.meta["backoff_decision"] = ("give_up", "retry_after_too_long")
            return

        if retry_after is not None:
            wait = retry_after
            self.stats.inc_value(f"backoff/retry_after/{key}")
        else:
            wait = min(self.base * 2**attempt, self.max_wait) * random.uniform(1.0, 1.2)
            self.stats.inc_value(f"backoff/exponential/{key}")

        # The downloader waits until lastseen + delay before sending the next
        # request from a slot. Moving lastseen forward pauses the whole host.
        # It also keeps the slot from being cleaned up while paused.
        slot = self.crawler.engine.downloader.slots.get(key)
        if slot is not None:
            slot.lastseen = max(slot.lastseen, time.monotonic() + wait)

        request.meta["backoff_decision"] = ("retry", wait)
        self.stats.inc_value(f"backoff/status_{response.status}/{key}")
        logger.info(
            "%s from %s, pausing host %.1fs (attempt %d)",
            response.status, key, wait, attempt + 1,
        )

    def process_response(self, request, response):
        decision = request.meta.pop("backoff_decision", None)
        if decision is None:
            return response

        action, detail = decision
        if action == "give_up":
            key = request.meta.get("download_slot")
            self.stats.inc_value(f"backoff/gave_up/{detail}/{key}")
            logger.warning("Giving up on %s after %s (%s)", request.url, response.status, detail)
            return response

        retry = request.copy()
        retry.meta["backoff_attempt"] = request.meta.get("backoff_attempt", 0) + 1
        retry.dont_filter = True  # the dupefilter has already seen this URL
        return retry
