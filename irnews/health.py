import logging
from datetime import datetime, timezone

from scrapy import signals

from irnews.store import open_db

logger = logging.getLogger(__name__)


class HealthCheck:
    """After each crawl, check every ticker for silent failures.

    A broken crawler rarely crashes. It finishes normally and stores nothing, or
    stores the wrong thing. And because crawls are incremental, "0 new items" is
    also what a healthy run looks like when a company published nothing. So none
    of these checks count items. They look at signals that do not depend on how
    much news there was:

    listing_not_reached     no listing page was parsed: blocked, 404, robots.txt
    listing_empty           page 1 of the listing had no links: the selector stopped matching
    links_per_page_dropped  under half the links per page of the last run: partial template change
    high_drop_rate          too many detail pages failed validation: detail template change
    low_coverage            a body kept too little of its article: extraction bug

    Results go to the crawl_runs table and to the log, as ERROR when a check fails.
    """

    def __init__(self, crawler):
        self.crawler = crawler
        self.stats = crawler.stats
        settings = crawler.settings
        self.db_path = settings.get("SQLITE_PATH")
        self.max_drop_rate = settings.getfloat("HEALTH_MAX_DROP_RATE")
        self.min_links_ratio = settings.getfloat("HEALTH_MIN_LINKS_RATIO")
        crawler.signals.connect(self.spider_closed, signal=signals.spider_closed)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def spider_closed(self, spider, reason):
        tickers = getattr(spider, "sites", None)
        if not tickers:
            return
        run_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conn = open_db(self.db_path)
        for ticker in tickers:
            self.check_ticker(conn, run_at, ticker)
        conn.commit()
        conn.close()

    def check_ticker(self, conn, run_at, ticker):
        get = lambda key: self.stats.get_value(f"{key}/{ticker}", 0)  # noqa: E731
        pages = get("listing/pages")
        empty = get("listing/empty")
        links = get("listing/links")
        ok = get("validate/ok")
        dropped = sum(
            value for key, value in self.stats.get_stats().items()
            if key.startswith("validate/") and key.endswith(f"/{ticker}")
            and not key.startswith("validate/ok/")
        )
        low_coverage = get("quality/low_coverage")

        failed = []
        if pages == 0 and empty == 0:
            failed.append("listing_not_reached")
        if empty > 0:
            failed.append("listing_empty")
        previous = conn.execute(
            "SELECT listing_pages, listing_links FROM crawl_runs"
            " WHERE ticker = ? AND listing_pages > 0 ORDER BY run_at DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        if pages > 0 and previous:
            before = previous[1] / previous[0]
            now = links / pages
            if now < before * self.min_links_ratio:
                failed.append("links_per_page_dropped")
        if dropped and dropped / (dropped + ok) > self.max_drop_rate:
            failed.append("high_drop_rate")
        if low_coverage:
            failed.append("low_coverage")

        status = "failed" if failed else "ok"
        conn.execute(
            "INSERT INTO crawl_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run_at, ticker, pages, links, ok, dropped, low_coverage,
             get("store/inserted"), status, ",".join(failed)),
        )
        self.stats.set_value(f"health/status/{ticker}", status)
        for name in failed:
            self.stats.set_value(f"health/failed/{name}/{ticker}", 1)
        if failed:
            logger.error("HEALTH FAILED for %s: %s", ticker, ", ".join(failed))
        else:
            logger.info("Health ok for %s", ticker)
