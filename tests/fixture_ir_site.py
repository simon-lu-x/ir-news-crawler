"""A local IR news site laid out like ir.amd.com, or like www.intc.com.

Listing pages are newest first, PER_PAGE items each, at /news?page=N.
Detail pages live at /news/detail/<id>/release-<id>. Change `ids` between
crawls to simulate new releases.
"""

from urllib.parse import parse_qs, urlparse

from tests.fixture_site import FixtureSite

PER_PAGE = 3
BODY = "This is a press release paragraph with enough words to pass validation. " * 5
# A table, so extraction that drops tables shows up as low coverage.
TABLE = (
    "<table><tr><th>Metric</th><th>This quarter</th><th>Last quarter</th></tr>"
    + "".join(f"<tr><td>Line item {n} revenue</td><td>${n},000</td><td>${n},100</td></tr>" for n in range(1, 16))
    + "</table>"
)


class IRSite(FixtureSite):
    def __init__(self, ids, layout="amd"):
        self.ids = list(ids)  # newest first
        self.layout = layout
        # Switches to simulate failures between crawls.
        self.per_page = PER_PAGE
        self.listing_status = 200  # e.g. 403 for a blocked listing
        self.detail_title = True  # False drops the <h1>, so validation fails
        super().__init__(responder=self._respond)
        self.listing_url = f"{self.base_url}/news-events/press-releases"

    def _respond(self, path, hit_number):
        parsed = urlparse(path)
        if parsed.path == "/news-events/press-releases":
            if self.listing_status != 200:
                return self.listing_status, {}, "blocked"
            page = int(parse_qs(parsed.query).get("page", ["1"])[0])
            start = (page - 1) * self.per_page
            return 200, {}, self._listing(self.ids[start:start + self.per_page])
        if parsed.path.startswith("/news-events/press-releases/detail/"):
            release_id = parsed.path.split("/")[4]
            return 200, {}, self._detail(release_id)
        return 404, {}, "not found"

    def _listing(self, ids):
        if self.layout == "intel":
            return self._intel_listing(ids)
        items = "".join(
            f'<article class="media"><div class="media-heading">'
            f'<a href="{self.base_url}/news-events/press-releases/detail/{i}/release-{i}">Release {i}</a>'
            f"</div></article>"
            for i in ids
        )
        return f"<html><body>{items}</body></html>"

    def _intel_listing(self, ids):
        # Three links per release, like the real site: image, title, button.
        items = []
        for i in ids:
            href = f"{self.base_url}/news-events/press-releases/detail/{i}/release-{i}"
            items.append(
                f'<article class="media-container">'
                f'<div class="media-image"><a href="{href}"><img alt="Release {i}"></a></div>'
                f'<div class="media-description"><div class="media-title"><a href="{href}">Release {i}</a></div>'
                f"<a class='btn' href=\"{href}\">View Press Release</a></div></article>"
            )
        return f"<html><body>{''.join(items)}</body></html>"

    def _detail(self, release_id):
        url = f"{self.base_url}/news-events/press-releases/detail/{release_id}/release-{release_id}"
        h1 = f'<h1 class="article-heading">Release {release_id}</h1>' if self.detail_title else ""
        if self.layout == "intel":
            return (
                f'<html><head><link rel="canonical" href="{url}"></head><body>'
                f'<article class="full-news-article">'
                f'<div class="related-documents box hidden-print">Related Documents 10-K Filing PDF</div>'
                f"{h1}"
                f'<div class="related-documents-line hidden-print">'
                f'<time datetime="2026-09-{int(release_id):02d}T09:00:00" class="date pull-left">x</time></div>'
                f"<p>{BODY} Release number {release_id}.</p>{TABLE}"
                f'<p class="spr-ir-news-article-date">Released Sep {int(release_id)}, 2026</p>'
                f"</article></body></html>"
            )
        return (
            f'<html><head><link rel="canonical" href="{url}"></head><body>'
            f'<article class="full-news-article">{h1}'
            f'<time class="date" datetime="2026-09-{int(release_id):02d}T09:00:00">x</time>'
            f"<p>{BODY} Release number {release_id}.</p>{TABLE}</article></body></html>"
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
