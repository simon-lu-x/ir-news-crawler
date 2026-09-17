import hashlib
import sqlite3
from pathlib import Path

from scrapy.exceptions import DropItem

SCHEMA = """
CREATE TABLE IF NOT EXISTS press_releases (
    url           TEXT PRIMARY KEY,
    ticker        TEXT NOT NULL,
    source_id     TEXT,
    title         TEXT NOT NULL,
    published_at  TEXT NOT NULL,
    body_text     TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_content_hash ON press_releases(content_hash);
"""


def open_db(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


class ValidatePipeline:
    """Drop items that are missing a required field.

    A crawler rarely crashes when a site changes its layout. It keeps running and
    returns empty titles or empty bodies. So we check the shape of every item and
    count each reason, which the run summary can then alert on.
    """

    REQUIRED = ("title", "published_at", "body_text")

    def __init__(self, stats, min_body_chars):
        self.stats = stats
        self.min_body_chars = min_body_chars

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.stats, crawler.settings.getint("MIN_BODY_CHARS"))

    def process_item(self, item):
        ticker = item.get("ticker")
        for field in self.REQUIRED:
            if not item.get(field):
                self.stats.inc_value(f"validate/missing_{field}/{ticker}")
                raise DropItem(f"missing {field}: {item.get('url')}")
        if len(item["body_text"]) < self.min_body_chars:
            self.stats.inc_value(f"validate/short_body/{ticker}")
            raise DropItem(f"body too short: {item.get('url')}")
        self.stats.inc_value(f"validate/ok/{ticker}")
        return item


class ContentDedupPipeline:
    """Drop a release whose text we already stored under a different URL.

    URL dedup is not enough. The same release can live at two URLs. The request
    fingerprint and the url primary key cannot see that, but a hash of the text can.
    """

    def __init__(self, stats, db_path):
        self.stats = stats
        self.db_path = db_path

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.stats, crawler.settings.get("SQLITE_PATH"))

    def open_spider(self):
        conn = open_db(self.db_path)
        # hash -> url. Loading everything is fine for thousands of rows.
        # At millions of rows this would move to an indexed lookup or a Bloom filter.
        self.seen = dict(conn.execute("SELECT content_hash, url FROM press_releases"))
        conn.close()

    def process_item(self, item):
        normalized = " ".join(item["body_text"].lower().split())
        content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        item["content_hash"] = content_hash

        first_url = self.seen.get(content_hash)
        if first_url is not None and first_url != item["url"]:
            self.stats.inc_value(f"dedup/same_content_other_url/{item['ticker']}")
            raise DropItem(f"same content as {first_url}: {item['url']}")

        self.seen[content_hash] = item["url"]
        return item


class SQLitePipeline:
    """Write items idempotently. Running the crawl twice gives the same rows."""

    def __init__(self, stats, db_path):
        self.stats = stats
        self.db_path = db_path

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.stats, crawler.settings.get("SQLITE_PATH"))

    def open_spider(self):
        self.conn = open_db(self.db_path)

    def close_spider(self):
        self.conn.commit()
        self.conn.close()

    def process_item(self, item):
        is_new = (
            self.conn.execute(
                "SELECT 1 FROM press_releases WHERE url = ?", (item["url"],)
            ).fetchone()
            is None
        )
        # Upsert. A new URL is inserted. A known URL only refreshes its fields and
        # last_seen_at, and keeps its original first_seen_at.
        self.conn.execute(
            """
            INSERT INTO press_releases
                (url, ticker, source_id, title, published_at, body_text,
                 content_hash, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title        = excluded.title,
                published_at = excluded.published_at,
                body_text    = excluded.body_text,
                content_hash = excluded.content_hash,
                last_seen_at = excluded.last_seen_at
            """,
            (
                item["url"], item["ticker"], item["source_id"], item["title"],
                item["published_at"], item["body_text"], item["content_hash"],
                item["fetched_at"], item["fetched_at"],
            ),
        )
        self.stats.inc_value(f"store/{'inserted' if is_new else 'updated'}/{item['ticker']}")
        return item
