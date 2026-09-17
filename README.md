# ir-news-crawler

**English** | [中文](README.zh-CN.md)

Collects press releases from the investor relations sites of US listed companies and stores them in SQLite.

[![test](https://github.com/simon-lu-x/ir-news-crawler/actions/workflows/test.yml/badge.svg)](https://github.com/simon-lu-x/ir-news-crawler/actions/workflows/test.yml)

Status: stage 6. Two companies (AMD, Intel) on two page templates, listing pages to storage. Crawl-delay is enforced. 429 and 503 pause the host. Crawls are incremental. Every run is checked for silent failures.

What building it turned up (details in [Findings so far](#findings-so-far)):

- Scrapy parses `Crawl-delay` but never enforces it, and AutoThrottle can lower the delay below it.
- On a 429, delaying the retry is not enough. Requests already queued for that host still go out, so the whole host has to pause.
- A broken crawler still ends with `finish_reason: finished`. A `<p>`-only parser silently dropped about 70% of an earnings release, so every run is now checked for silent failures.
- robots.txt allowing a path does not mean you get in. 19 of 35 IR sites checked were behind bot protection.

## Run

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/scrapy crawl press_detail -a max_pages=1
.venv/bin/scrapy crawl press_detail -a tickers=INTC -a max_pages=1
.venv/bin/scrapy crawl press_detail -a max_pages=1 -a full=1   # ignore what is stored
sqlite3 data/irnews.db "select source_id, published_at, title from press_releases"
sqlite3 data/irnews.db "select run_at, ticker, status, failed_checks from crawl_runs"
```

## Sample output

From a local run on 2026-09-17. The database is not in the repo (`data/` is ignored), so this is a copy.

`press_releases`: 44 rows (AMD 20, INTC 24). The newest five:

```
ticker  source_id  published   title
------  ---------  ----------  ------------------------------------------------------------------
INTC    1781       2026-09-08  Intel Foundry and ASML Collaborate to Accelerate Industry Readiness for High NA EUV
AMD     1298       2026-08-31  AMD, Cisco and HUMAIN Expand Saudi Arabia's AI Infrastructure as AMD Instinct Systems Go Live
AMD     1297       2026-08-19  AMD Appoints Tim Ryan to Board of Directors
INTC    1780       2026-08-18  Intel Corporation to Participate in Upcoming Investor Conference
INTC    1779       2026-08-11  Intel Announces Upsize and Pricing of $20 Billion Common Stock Offering
```

Part of the stored body of "AMD Reports Second Quarter 2026 Financial Results". Table rows are kept, one line per row. The `<p>`-only parser lost all of these:

```
 | Q2'26 | Q2'25 (1) | Y/Y ( 1) | Q1'26 | Q/Q
Revenue ($M) | $11,536 | $7,685 | Up 50% | $10,253 | Up 13%
Gross profit ($M) | $6,203 | $3,059 | Up 103% | $5,416 | Up 15%
Net income ($M) | $2,297 | $872 | Up 163% | $1,383 | Up 66%
```

`crawl_runs`: the health check result per ticker. The first run fetched releases that were already stored, so rows were updated, not inserted. The second run was incremental: page 1 had no new ids, so it stopped there and fetched no detail pages.

```
run_at                     ticker  pages  links  details_ok  inserted  status
-------------------------  ------  -----  -----  ----------  --------  ------
2026-09-17T05:40:17+00:00  AMD     2      20     20          0         ok
2026-09-17T05:40:17+00:00  INTC    2      24     24          0         ok
2026-09-17T05:43:34+00:00  AMD     1      10     0           0         ok
2026-09-17T05:43:34+00:00  INTC    1      12     0           0         ok
```

## Test

```
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

Tests run the real crawler in a subprocess against a small local site (`tests/fixture_site.py`) that records when each request arrives.

## Components

| Component | In Scrapy | In this repo |
|---|---|---|
| Seeds | `start()` | `SITES` in `spiders/press_detail.py` |
| Per-template selectors | CSS selectors in callbacks | `LAYOUTS` in `spiders/press_detail.py` |
| URL frontier | Scheduler | built in |
| Fetcher | Downloader | built in |
| Politeness | download slots per hostname, AutoThrottle | `settings.py` |
| Crawl-delay | parsed but not enforced, added here | `CrawlDelayAutoThrottle` in `extensions.py` |
| Retry with backoff | `RetryMiddleware` retries at once, added here | `RateLimitBackoffMiddleware` in `middlewares.py` |
| robots.txt handler | `RobotsTxtMiddleware` | `ROBOTSTXT_OBEY` |
| Parser and link extractor | Spider callbacks | `parse_listing`, `parse_detail` |
| URL canonicalizer | | `link[rel=canonical]` in `parse_detail` |
| Duplicate URL eliminator, within a run | request fingerprint dupefilter | built in |
| Duplicate URL eliminator, across runs | | `known_source_ids` in `store.py`, checked in `parse_listing` |
| Monitoring | stats collector | `HealthCheck` in `health.py`, results in `crawl_runs` |
| Recrawl policy | | stop paging at the first page with no new ids; `PARSER_VERSION` |
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

**Scrapy retries 429 with no backoff.** `RetryMiddleware` puts the request straight back in the queue and does not read `Retry-After`. `RateLimitBackoffMiddleware` pauses the whole host for as long as `Retry-After` says, or backs off exponentially when there is no header. It gives up if retries run out, or if the server asks for a longer wait than `BACKOFF_MAX`.

The first version paused requests in `process_request`, and its test failed: the other requests went out 0.2 seconds after the 429. Scrapy had already moved them past the middleware into the host's download slot queue. The pause now happens in the `response_downloaded` signal, which Scrapy sends before the slot picks its next request, by moving the slot's `lastseen` time forward.

Against a local site that returns one 429 with `Retry-After: 3`, then serves 4 pages:

| Retry | Seconds after the 429 | Sent too early |
|---|---|---|
| Stock RetryMiddleware, run 1 | 0.29, 0.51, 0.76, 1.02 | 4 of 4 |
| Stock RetryMiddleware, run 2 | 0.17, 0.40, 0.68, 0.96 | 4 of 4 |
| `RateLimitBackoffMiddleware`, run 1 | 3.30, 3.59, 3.86, 4.14 | 0 of 4 |
| `RateLimitBackoffMiddleware`, run 2 | 3.17, 3.43, 3.70, 3.92 | 0 of 4 |

**A crawler that is broken still finishes normally.** Blocked listings, selectors that stop matching, and extraction that drops text all end with `finish_reason: finished`. And with incremental crawls, zero new items is also what a healthy run looks like. So `HealthCheck` never counts items. After each run it checks every ticker for:

| Check | Catches | Rule |
|---|---|---|
| `listing_not_reached` | 403, 404, robots.txt | no listing page parsed |
| `listing_empty` | listing selector stopped matching | page 1 has no links |
| `links_per_page_dropped` | partial template change | under half the links per page of the last run |
| `high_drop_rate` | detail template change | over 20% of detail pages fail validation |
| `low_coverage` | extraction bug | a body keeps under 80% of its article's words |

`low_coverage` exists because of the table bug below. The word count of the article is computed separately from the extractor on purpose: if both used the same node selection, a selection bug would shrink both sides and the ratio would still look fine. On real pages:

| Page | Current parser | `<p>`-only parser |
|---|---|---|
| AMD Q2 2026 earnings | 1.00 | 0.26 |
| Intel Q2 2026 earnings | 1.00 | 0.27 |
| AMD board appointment | 1.00 | 0.94 |

All 44 AMD and Intel releases crawled scored 1.00.

The first version of `listing_empty` flagged any empty listing page. Its tests failed: a crawl that pages past the last page gets an empty page, which is just the end of the listing. A full AMD backfill would have hit the same false alarm on page 131. Now only an empty page 1 counts.

**Same platform does not mean same template.** AMD and Intel use the same IR platform, with the same URL scheme and the same asset CDN. The first try ran AMD's listing selector on Intel and found zero links. Intel's theme uses different listing markup, links each release three times (image, title, button), and adds a related documents box and a "Released" line to the article. So the parser is split by template, not by company: the crawl logic is shared, and each template is a few selectors in `LAYOUTS`. After the change, AMD's 20 stored rows re-parsed to identical content hashes, so `PARSER_VERSION` did not need a bump.

Two things a test should not trust here. Wrong selectors do not raise: the crawl finishes normally with zero items, and the only sign is the `listing/empty` stat. And Scrapy's dupefilter hides a listing selector that takes all three links per release, because each URL is still fetched once. The layout test checks `dupefilter/filtered` for that reason. Without that check, the test passed with the wrong selector.

**Incremental crawling needs a parser version.** A rerun skips releases whose site id is already stored, and stops paging at the first listing page with no new ids. Two runs on AMD: the first made 23 requests, the second made 2 (robots.txt and page 1).

It does not stop at the first known item, because a pinned or re-dated release can sit above new ones. And "already stored" means stored by the current `PARSER_VERSION`. Without that, the table fix below would never have reached rows saved before it. Those rows would count as done and never be fetched again.

**A long body can still be the wrong body.** The first parser read only `<p>` tags. On AMD's Q2 2026 earnings release that dropped 17 tables and about 70% of the text, including every net income figure. Title, date and length checks all passed, so nothing failed. The parser now reads every block in order and keeps table rows.

## Known issues

* Some financial tables split `$` and the number into separate cells, which leaves empty cells in a row.
* If a company edits a release after we store it, an incremental crawl does not see the change. `-a full=1` does.
* The stop rule assumes the listing is newest first.
* `low_coverage` at 80% misses small losses. The `<p>`-only parser lost 6% of a release with no tables, and that would pass.
* Health results go to the log and the `crawl_runs` table only. Nothing sends an alert yet, and the process exit code is 0 either way.
* `links_per_page_dropped` compares with the last run only.
* Backoff state lives in the download slot, so it only covers one crawler process. Several processes hitting the same host would need shared state, such as Redis.
* The idle-slot case (a slot dropped and rebuilt) is handled by writing to the downloader's per-slot settings, but it has no test yet. A test would need over a minute of idle time.

## Not built, on purpose

Proxy rotation, CAPTCHA solving, browser fingerprint spoofing. They are for getting past sites that have chosen to block automated access.
