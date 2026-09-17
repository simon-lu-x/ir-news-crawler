import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(cmd):
    """Run a crawl in its own process with the project settings.

    A separate process keeps each test independent. Scrapy's event loop can only
    start once per Python process.
    """
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stderr[-3000:]
    return result.stderr  # Scrapy logs to stderr


def _settings(settings):
    args = []
    for setting in settings:
        args += ["-s", setting]
    return args


def run_fixture_crawl(base_url, pages, *settings):
    """Run tests/fixture_spider.py, which fetches /page/0 .. /page/N-1."""
    return _run([
        sys.executable, "-m", "scrapy", "runspider", "tests/fixture_spider.py",
        "-a", f"base={base_url}", "-a", f"pages={pages}", *_settings(settings),
    ])


def run_press_crawl(sites, db_path, *spider_args, settings=()):
    """Run the real press_detail spider against `sites` ("TICKER=url")."""
    cmd = [
        sys.executable, "-m", "scrapy", "crawl", "press_detail",
        "-a", f"sites={sites}", "-s", f"SQLITE_PATH={db_path}", *_settings(settings),
    ]
    for arg in spider_args:
        cmd += ["-a", arg]
    return _run(cmd)


def stat(log, key):
    """Read one integer stat from the stats dump at the end of a Scrapy log."""
    match = re.search(rf"'{re.escape(key)}': (\d+)", log)
    return int(match.group(1)) if match else 0


def gaps(times):
    return [round(b - a, 2) for a, b in zip(times, times[1:])]
