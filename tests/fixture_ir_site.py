"""A local IR news site laid out like ir.amd.com.

Listing pages are newest first, PER_PAGE items each, at /news?page=N.
Detail pages live at /news/detail/<id>/release-<id>. Change `ids` between
crawls to simulate new releases.
"""

from urllib.parse import parse_qs, urlparse

from tests.fixture_site import FixtureSite

PER_PAGE = 3
BODY = "This is a press release paragraph with enough words to pass validation. " * 5


class IRSite(FixtureSite):
    def __init__(self, ids):
        self.ids = list(ids)  # newest first
        super().__init__(responder=self._respond)
        self.listing_url = f"{self.base_url}/news-events/press-releases"

    def _respond(self, path, hit_number):
        parsed = urlparse(path)
        if parsed.path == "/news-events/press-releases":
            page = int(parse_qs(parsed.query).get("page", ["1"])[0])
            start = (page - 1) * PER_PAGE
            return 200, {}, self._listing(self.ids[start:start + PER_PAGE])
        if parsed.path.startswith("/news-events/press-releases/detail/"):
            release_id = parsed.path.split("/")[4]
            return 200, {}, self._detail(release_id)
        return 404, {}, "not found"

    def _listing(self, ids):
        items = "".join(
            f'<article class="media"><div class="media-heading">'
            f'<a href="{self.base_url}/news-events/press-releases/detail/{i}/release-{i}">Release {i}</a>'
            f"</div></article>"
            for i in ids
        )
        return f"<html><body>{items}</body></html>"

    def _detail(self, release_id):
        url = f"{self.base_url}/news-events/press-releases/detail/{release_id}/release-{release_id}"
        return (
            f'<html><head><link rel="canonical" href="{url}"></head><body>'
            f'<article class="full-news-article"><h1 class="article-heading">Release {release_id}</h1>'
            f'<time class="date" datetime="2026-09-{int(release_id):02d}T09:00:00">x</time>'
            f"<p>{BODY} Release number {release_id}.</p></article></body></html>"
        )

    def detail_hits(self):
        return sorted(
            int(p.split("/")[4]) for p, _ in self.hits
            if p.startswith("/news-events/press-releases/detail/")
        )

    def listing_hits(self):
        return [p for p, _ in self.hits if p.startswith("/news-events/press-releases") and "/detail/" not in p]

    def reset_hits(self):
        self.hits.clear()
