import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run_fixture_crawl(base_url, pages, *settings):
    """Run the fixture spider in its own process with the project settings.

    A separate process keeps each test independent. Scrapy's event loop can only
    start once per Python process.
    """
    cmd = [
        sys.executable, "-m", "scrapy", "runspider", "tests/fixture_spider.py",
        "-a", f"base={base_url}", "-a", f"pages={pages}",
    ]
    for setting in settings:
        cmd += ["-s", setting]
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stderr[-3000:]
    return result.stderr  # Scrapy logs to stderr


def gaps(times):
    return [round(b - a, 2) for a, b in zip(times, times[1:])]
