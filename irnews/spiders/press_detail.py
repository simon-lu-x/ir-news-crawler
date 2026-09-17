"""Spider for IR sites whose press release URLs look like
/news-events/press-releases/detail/<numeric id>/<slug>.

AMD and Intel both use this layout, so one parser serves several companies.
Adding a company on the same platform is one line in SITES.

Crawls are incremental. A detail page is skipped when its id is already stored
by the current PARSER_VERSION. Paging stops at the first listing page with no
new ids. Pass -a full=1 to fetch everything again.
"""

import re
from datetime import datetime, timezone

import scrapy

from irnews.items import PressRelease
from irnews.store import known_source_ids

SITES = {
    "AMD": "https://ir.amd.com/news-events/press-releases",
}

DETAIL_ID = re.compile(r"/press-releases/detail/(\d+)/")

# Bump this whenever parse_detail or extract_body changes what gets stored.
# Rows saved by an older version count as not fetched, so they are parsed again.
# Version 1 read every block and kept tables. The earlier <p>-only parser had no version.
PARSER_VERSION = 1


class PressDetailSpider(scrapy.Spider):
    name = "press_detail"

    def __init__(self, tickers=None, max_pages=2, full=0, sites=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if sites:
            # For tests: "TICKER=url,TICKER=url" replaces SITES.
            self.sites = dict(pair.split("=", 1) for pair in sites.split(","))
        else:
            wanted = tickers.split(",") if tickers else list(SITES)
            self.sites = {t: SITES[t] for t in wanted}
        # Each listing page has 10 items. AMD has 130 pages, so we cap it while developing.
        self.max_pages = int(max_pages)
        self.full = bool(int(full))

    async def start(self):
        if self.full:
            self.known = {}
        else:
            self.known = known_source_ids(self.settings.get("SQLITE_PATH"), PARSER_VERSION)
        for ticker, url in self.sites.items():
            yield scrapy.Request(
                url, callback=self.parse_listing, cb_kwargs={"ticker": ticker, "page": 1}
            )

    def parse_listing(self, response, ticker, page):
        links = response.css("article.media .media-heading a::attr(href)").getall()
        if not links:
            # A listing page with no items means the layout changed or we got blocked.
            # Count it so the run summary shows it, instead of silently getting nothing.
            self.crawler.stats.inc_value(f"listing/empty/{ticker}")
            return

        self.crawler.stats.inc_value(f"listing/pages/{ticker}")
        known = self.known.get(ticker, set())
        new_count = 0
        for href in links:
            match = DETAIL_ID.search(href)
            if match and match.group(1) in known:
                self.crawler.stats.inc_value(f"incremental/skipped_known/{ticker}")
                continue
            # A link with no id cannot be checked, so it is always fetched.
            new_count += 1
            yield response.follow(
                href.strip(), callback=self.parse_detail, cb_kwargs={"ticker": ticker}
            )

        if new_count == 0 and not self.full:
            # The listing is newest first. A whole page of known items means the
            # pages after it are older still. Stopping at the first known item
            # would be too early: a pinned or re-dated release can sit above new ones.
            self.crawler.stats.set_value(f"incremental/stopped_at_page/{ticker}", page)
            return

        next_href = response.css("ul#pagination--desktop a[rel=next]::attr(href)").get()
        if next_href is None:
            next_href = f"{self.sites[ticker]}?page={page + 1}"
        if page < self.max_pages:
            yield response.follow(
                next_href,
                callback=self.parse_listing,
                cb_kwargs={"ticker": ticker, "page": page + 1},
            )

    def parse_detail(self, response, ticker):
        article = response.css("article.full-news-article")
        # Prefer the page's own canonical URL. The same release can be reached with
        # different query strings or slugs, and the canonical one is the stable key.
        url = response.css("link[rel=canonical]::attr(href)").get() or response.url
        match = DETAIL_ID.search(url)

        yield PressRelease(
            ticker=ticker,
            source_id=match.group(1) if match else None,
            url=url,
            title=(article.css("h1.article-heading::text").get() or "").strip(),
            published_at=article.css("time.date::attr(datetime)").get(),
            body_text=extract_body(article),
            fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            parser_version=PARSER_VERSION,
        )


def clean(texts):
    return " ".join(" ".join(texts).split())


def extract_body(article):
    """Return the article text, one block per line, tables kept row by row.

    An earlier version read only <p> tags. On an earnings release that dropped
    17 tables and about 70% of the text, and nothing failed. The item still had
    a title, a date and a long enough body, so validation passed.
    """
    blocks = []
    for node in article.xpath("./*"):
        tag = node.root.tag
        if tag == "h1" or "related-documents-line" in (node.attrib.get("class") or ""):
            continue  # title and the PDF link, stored elsewhere
        if tag == "table":
            for row in node.xpath(".//tr"):
                cells = [clean(cell.xpath(".//text()").getall()) for cell in row.xpath("./td|./th")]
                if any(cells):
                    blocks.append(" | ".join(cells))
        else:
            text = clean(node.xpath(".//text()[not(ancestor::script) and not(ancestor::style)]").getall())
            if text:
                blocks.append(text)
    return "\n".join(blocks)
