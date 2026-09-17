"""Fetches /page/0 .. /page/N-1 from a fixture site, one after another."""

import scrapy


class FixtureSpider(scrapy.Spider):
    name = "fixture"
    custom_settings = {"ITEM_PIPELINES": {}, "LOG_LEVEL": "INFO"}

    def __init__(self, base, pages=4, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.base = base
        self.pages = int(pages)

    async def start(self):
        for i in range(self.pages):
            yield scrapy.Request(f"{self.base}/page/{i}", callback=self.parse)

    def parse(self, response):
        self.crawler.stats.inc_value("fixture/pages_ok")
