# ir-news-crawler

Collects press releases from the investor relations sites of US listed companies and stores them in SQLite.

Status: stage 2. One company (AMD), listing pages to storage. Crawl-delay is enforced.

## Run

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/scrapy crawl press_detail -a max_pages=1
sqlite3 data/irnews.db "select source_id, published_at, title from press_releases"
```

## Test

```
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

Tests run the real crawler in a subprocess against a small local site (`tests/fixture_site.py`) that records when each request arrives.

## Components

| Textbook name | Scrapy name | Where |
|---|---|---|
| Seeds | `start()` | `SITES` in `spiders/press_detail.py` |
| URL frontier | Scheduler | built in |
| Fetcher | Downloader | built in |
| Politeness | download slots per hostname, AutoThrottle | `settings.py` |
| Crawl-delay | not supported, added here | `CrawlDelayAutoThrottle` in `extensions.py` |
| robots.txt handler | `RobotsTxtMiddleware` | `ROBOTSTXT_OBEY` |
| Parser and link extractor | Spider callbacks | `parse_listing`, `parse_detail` |
| URL canonicalizer | | `link[rel=canonical]` in `parse_detail` |
| Duplicate URL eliminator, within a run | request fingerprint dupefilter | built in |
| Content-seen test | Item Pipeline | `ContentDedupPipeline` |
| Validation | Item Pipeline | `ValidatePipeline` |
| Store | Item Pipeline | `SQLitePipeline`, upsert on `url` |

## Findings so far

**robots.txt allowing a path does not mean the server lets you in.** Of 35 large US companies checked, 19 IR sites returned a Cloudflare JavaScript challenge, an Akamai denial, or a CAPTCHA, even where robots.txt said `Allow: /`. Fifteen of them serve an identical robots.txt, which points to one shared hosting platform. This project does not try to get past bot protection. Those sites are out of scope.

**Scrapy does not enforce `Crawl-delay`.** In Scrapy 2.19 the robots parsers expose `crawl_delay()`, but nothing in the framework calls it. Several IR sites set `Crawl-delay: 10`.

Setting a slot's delay once is not enough, because three things undo it. AutoThrottle rewrites the delay after every response, with the global `DOWNLOAD_DELAY` as its only floor. Each slot adds ±50% random jitter. And an idle slot is dropped after about 60 seconds, then rebuilt with the default delay. `CrawlDelayAutoThrottle` handles all three.

Against a local site with `Crawl-delay: 3`, over 5 gaps between requests:

| Throttle | Gaps (seconds) | Under 3s |
|---|---|---|
| Stock AutoThrottle, run 1 | 2.10, 2.24, 2.45, 2.99, 2.70 | 4 of 5 |
| Stock AutoThrottle, run 2 | 2.97, 2.96, 2.96, 2.51, 2.66 | 2 of 5 |
| `CrawlDelayAutoThrottle`, 2 runs | 3.00 every time | 0 of 5 |

**Scrapy retries 429 with no backoff.** `RetryMiddleware` does not read `Retry-After`.

**A long body can still be the wrong body.** The first parser read only `<p>` tags. On AMD's Q2 2026 earnings release that dropped 17 tables and about 70% of the text, including every net income figure. Title, date and length checks all passed, so nothing failed. The parser now reads every block in order and keeps table rows.

## Known issues

* Some financial tables split `$` and the number into separate cells, which leaves empty cells in a row.
* A rerun fetches every detail page again, even ones already stored.
* The idle-slot case (a slot dropped and rebuilt) is handled by writing to the downloader's per-slot settings, but it has no test yet. A test would need over a minute of idle time.

## Not built, on purpose

Proxy rotation, CAPTCHA solving, browser fingerprint spoofing. They are for getting past sites that have chosen to block automated access.
