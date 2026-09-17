import scrapy


class PressRelease(scrapy.Item):
    ticker = scrapy.Field()
    source_id = scrapy.Field()  # the site's own numeric id, when it has one
    url = scrapy.Field()  # canonical URL
    title = scrapy.Field()
    published_at = scrapy.Field()  # ISO 8601 string as the site gives it
    body_text = scrapy.Field()
    fetched_at = scrapy.Field()
    content_hash = scrapy.Field()  # set by ContentDedupPipeline
    parser_version = scrapy.Field()  # bump when parsing changes, so old rows get fetched again
