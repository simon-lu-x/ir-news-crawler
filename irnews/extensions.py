import logging

from scrapy import signals
from scrapy.extensions.throttle import AutoThrottle

logger = logging.getLogger(__name__)


class CrawlDelayAutoThrottle(AutoThrottle):
    """AutoThrottle that also respects the Crawl-delay in robots.txt.

    Scrapy 2.19 parses Crawl-delay but never uses it. Adding it is not just a
    matter of setting a slot's delay, because three things undo that:

    1. AutoThrottle rewrites slot.delay after every response. Its only floor is
       the global DOWNLOAD_DELAY, so it pulls a 10 second delay back down.
    2. Each slot adds random jitter, +/-50% by default. 10 seconds can become 5.
    3. The downloader drops a slot after about 60 idle seconds. A new slot for the
       same host starts again from the default delay.

    So the Crawl-delay becomes a per-host floor (fixes 1), the host's jitter is
    turned off (fixes 2), and both are written into the per-slot settings the
    downloader reads when it creates a slot (fixes 3).
    """

    def __init__(self, crawler):
        super().__init__(crawler)
        self.user_agent = (
            crawler.settings.get("ROBOTSTXT_USER_AGENT") or crawler.settings.get("USER_AGENT")
        )
        self.floors = {}  # slot key (hostname) -> seconds
        crawler.signals.connect(self._robots_parsed, signal=signals.robots_parsed)

    def _robots_parsed(self, robotparser, request):
        delay = robotparser.crawl_delay(self.user_agent)
        if not delay:
            return
        downloader = self.crawler.engine.downloader
        key = downloader.get_slot_key(request)
        self.floors[key] = float(delay)
        downloader.per_slot_settings[key] = {"delay": float(delay), "jitter": 0}

        slot = downloader.slots.get(key)
        if slot is not None:
            slot.delay = max(slot.delay, float(delay))
            slot.jitter = 0

        self.crawler.stats.set_value(f"robotstxt/crawl_delay/{key}", float(delay))
        logger.info("Crawl-delay %ss for %s", delay, key)

    def _response_downloaded(self, response, request, spider):
        super()._response_downloaded(response, request, spider)
        key = request.meta.get("download_slot")
        floor = self.floors.get(key)
        if floor is None:
            return
        slot = self.crawler.engine.downloader.slots.get(key)
        if slot is not None and slot.delay < floor:
            slot.delay = floor
