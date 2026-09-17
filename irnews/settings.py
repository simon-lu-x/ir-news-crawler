BOT_NAME = "irnews"
SPIDER_MODULES = ["irnews.spiders"]
NEWSPIDER_MODULE = "irnews.spiders"

# Say who we are and how to reach us. We never pretend to be a browser.
USER_AGENT = "irnews-research-crawler/0.1 (+mailto:lusicong22@gmail.com)"

# Politeness.
# robots.txt decides which paths we may fetch.
ROBOTSTXT_OBEY = True
# Scrapy groups requests into one "slot" per hostname. These limits apply per slot.
CONCURRENT_REQUESTS_PER_DOMAIN = 1
DOWNLOAD_DELAY = 2
# AutoThrottle raises the delay when the server gets slower. It never goes below DOWNLOAD_DELAY.
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 2
AUTOTHROTTLE_MAX_DELAY = 30
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
# Scrapy parses Crawl-delay but ignores it. This replaces AutoThrottle with a
# version that treats each host's Crawl-delay as a floor. See irnews/extensions.py.
EXTENSIONS = {
    "scrapy.extensions.throttle.AutoThrottle": None,
    "irnews.extensions.CrawlDelayAutoThrottle": 0,
    "irnews.health.HealthCheck": 500,
}

# Silent failure checks run at the end of every crawl. See irnews/health.py.
HEALTH_MIN_COVERAGE = 0.8  # a body must keep 80% of its article's words
HEALTH_MAX_DROP_RATE = 0.2  # at most 20% of detail pages may fail validation
HEALTH_MIN_LINKS_RATIO = 0.5  # links per listing page may not halve since the last run

# Retries. The built-in middleware retries these codes right away, with no backoff.
RETRY_ENABLED = True
RETRY_TIMES = 3
# 429 and 503 are left out here. RateLimitBackoffMiddleware handles them.
RETRY_HTTP_CODES = [500, 502, 504, 522, 524, 408]
DOWNLOAD_TIMEOUT = 20

# Backoff for 429 and 503. See irnews/middlewares.py.
DOWNLOADER_MIDDLEWARES = {
    "irnews.middlewares.RateLimitBackoffMiddleware": 540,
}
BACKOFF_BASE = 5
BACKOFF_MAX = 300
BACKOFF_MAX_RETRIES = 5

# Item pipeline. Lower number runs first.
ITEM_PIPELINES = {
    "irnews.pipelines.ValidatePipeline": 100,
    "irnews.pipelines.ContentDedupPipeline": 200,
    "irnews.pipelines.SQLitePipeline": 300,
}
SQLITE_PATH = "data/irnews.db"
MIN_BODY_CHARS = 200

LOG_LEVEL = "INFO"
