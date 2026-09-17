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

# Retries. The built-in middleware retries these codes right away, with no backoff.
RETRY_ENABLED = True
RETRY_TIMES = 3
DOWNLOAD_TIMEOUT = 20

# Item pipeline. Lower number runs first.
ITEM_PIPELINES = {
    "irnews.pipelines.ValidatePipeline": 100,
    "irnews.pipelines.ContentDedupPipeline": 200,
    "irnews.pipelines.SQLitePipeline": 300,
}
SQLITE_PATH = "data/irnews.db"
MIN_BODY_CHARS = 200

LOG_LEVEL = "INFO"
