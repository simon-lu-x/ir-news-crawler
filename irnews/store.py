import sqlite3
from collections import defaultdict
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS press_releases (
    url            TEXT PRIMARY KEY,
    ticker         TEXT NOT NULL,
    source_id      TEXT,
    title          TEXT NOT NULL,
    published_at   TEXT NOT NULL,
    body_text      TEXT NOT NULL,
    content_hash   TEXT NOT NULL,
    first_seen_at  TEXT NOT NULL,
    last_seen_at   TEXT NOT NULL,
    parser_version INTEGER
);
CREATE INDEX IF NOT EXISTS idx_content_hash ON press_releases(content_hash);
CREATE INDEX IF NOT EXISTS idx_ticker_source_id ON press_releases(ticker, source_id);

-- One row per ticker per crawl, written by HealthCheck.
CREATE TABLE IF NOT EXISTS crawl_runs (
    run_at          TEXT NOT NULL,
    ticker          TEXT NOT NULL,
    listing_pages   INTEGER NOT NULL,
    listing_links   INTEGER NOT NULL,
    details_ok      INTEGER NOT NULL,
    details_dropped INTEGER NOT NULL,
    low_coverage    INTEGER NOT NULL,
    inserted        INTEGER NOT NULL,
    status          TEXT NOT NULL,
    failed_checks   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_crawl_runs_ticker ON crawl_runs(ticker, run_at);
"""


def open_db(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    # Databases made before stage 4 lack parser_version. CREATE TABLE IF NOT EXISTS
    # does not change an existing table, so the column is added here.
    columns = {row[1] for row in conn.execute("PRAGMA table_info(press_releases)")}
    if columns and "parser_version" not in columns:
        conn.execute("ALTER TABLE press_releases ADD COLUMN parser_version INTEGER")
    conn.executescript(SCHEMA)
    return conn


def known_source_ids(path, parser_version):
    """Return {ticker: set of source ids} stored by this parser version.

    Rows from an older parser version are left out on purpose, so they get
    fetched and parsed again.
    """
    known = defaultdict(set)
    if not Path(path).exists():
        return known
    conn = open_db(path)
    rows = conn.execute(
        "SELECT ticker, source_id FROM press_releases"
        " WHERE source_id IS NOT NULL AND parser_version = ?",
        (parser_version,),
    )
    for ticker, source_id in rows:
        known[ticker].add(source_id)
    conn.close()
    return known
