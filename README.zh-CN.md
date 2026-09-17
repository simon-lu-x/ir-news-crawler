# ir-news-crawler

[English](README.md) | **中文**

从美国上市公司的投资者关系（IR）网站抓取新闻稿，存进 SQLite。

[![test](https://github.com/simon-lu-x/ir-news-crawler/actions/workflows/test.yml/badge.svg)](https://github.com/simon-lu-x/ir-news-crawler/actions/workflows/test.yml)

当前进度：第 6 阶段。覆盖两家公司（AMD、Intel），对应两种页面模板，从列表页一路抓到入库。遵守 Crawl-delay。遇到 429 和 503 会暂停整个站点。增量抓取。每次运行结束都检查有没有静默失败。

开发过程中发现的问题（详见[目前的发现](#目前的发现)）：

- Scrapy 能解析 `Crawl-delay`，但从来不执行；AutoThrottle 还可能把间隔调到它以下。
- 收到 429 时，只推迟这一次重试不够。同一站点已经排进队列的请求照样会发出去，所以必须暂停整个站点。
- 爬虫坏了，照样以 `finish_reason: finished` 正常结束。只读 `<p>` 的解析器悄无声息地丢掉了一篇财报约 70% 的内容，所以现在每次运行都做静默失败检查。
- robots.txt 允许访问，不代表进得去。查过的 35 个 IR 网站里，有 19 个挡在反爬防护后面。

## 运行

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/scrapy crawl press_detail -a max_pages=1
.venv/bin/scrapy crawl press_detail -a tickers=INTC -a max_pages=1
.venv/bin/scrapy crawl press_detail -a max_pages=1 -a full=1   # 忽略已存数据，全部重抓
sqlite3 data/irnews.db "select source_id, published_at, title from press_releases"
sqlite3 data/irnews.db "select run_at, ticker, status, failed_checks from crawl_runs"
```

## 示例输出

来自 2026-09-17 的一次本地运行。数据库不在仓库里（`data/` 被 git 忽略），下面是复制出来的结果。

`press_releases` 表：共 44 行（AMD 20 行，INTC 24 行）。最新 5 条：

```
ticker  source_id  published   title
------  ---------  ----------  ------------------------------------------------------------------
INTC    1781       2026-09-08  Intel Foundry and ASML Collaborate to Accelerate Industry Readiness for High NA EUV
AMD     1298       2026-08-31  AMD, Cisco and HUMAIN Expand Saudi Arabia's AI Infrastructure as AMD Instinct Systems Go Live
AMD     1297       2026-08-19  AMD Appoints Tim Ryan to Board of Directors
INTC    1780       2026-08-18  Intel Corporation to Participate in Upcoming Investor Conference
INTC    1779       2026-08-11  Intel Announces Upsize and Pricing of $20 Billion Common Stock Offering
```

"AMD Reports Second Quarter 2026 Financial Results" 入库正文的一部分。表格按行保留，一行一条。只读 `<p>` 的解析器会把这些全部丢掉：

```
 | Q2'26 | Q2'25 (1) | Y/Y ( 1) | Q1'26 | Q/Q
Revenue ($M) | $11,536 | $7,685 | Up 50% | $10,253 | Up 13%
Gross profit ($M) | $6,203 | $3,059 | Up 103% | $5,416 | Up 15%
Net income ($M) | $2,297 | $872 | Up 163% | $1,383 | Up 66%
```

`crawl_runs` 表：每家公司每次运行的健康检查结果。第一次运行抓到的新闻库里已经有了，所以是更新，不是新增。第二次是增量抓取：第 1 页没有新 id，就在那里停下，没有抓任何详情页。

```
run_at                     ticker  pages  links  details_ok  inserted  status
-------------------------  ------  -----  -----  ----------  --------  ------
2026-09-17T05:40:17+00:00  AMD     2      20     20          0         ok
2026-09-17T05:40:17+00:00  INTC    2      24     24          0         ok
2026-09-17T05:43:34+00:00  AMD     1      10     0           0         ok
2026-09-17T05:43:34+00:00  INTC    1      12     0           0         ok
```

## 测试

```
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

测试会在子进程里运行真实的爬虫，目标是一个本地小网站（`tests/fixture_site.py`），它会记录每个请求到达的时间。

## 组件

| 组件 | Scrapy 中对应 | 本仓库中位置 |
|---|---|---|
| 种子 URL | `start()` | `spiders/press_detail.py` 里的 `SITES` |
| 按模板区分的选择器 | 回调里的 CSS 选择器 | `spiders/press_detail.py` 里的 `LAYOUTS` |
| URL 待抓队列（frontier） | Scheduler | 框架自带 |
| 下载器 | Downloader | 框架自带 |
| 礼貌抓取 | 按域名划分的下载 slot、AutoThrottle | `settings.py` |
| Crawl-delay | 能解析但不执行，本项目补上 | `extensions.py` 里的 `CrawlDelayAutoThrottle` |
| 带退避的重试 | `RetryMiddleware` 立即重试，本项目补上 | `middlewares.py` 里的 `RateLimitBackoffMiddleware` |
| robots.txt 处理 | `RobotsTxtMiddleware` | `ROBOTSTXT_OBEY` |
| 解析器与链接提取 | Spider 回调 | `parse_listing`、`parse_detail` |
| URL 规范化 | | `parse_detail` 里读 `link[rel=canonical]` |
| URL 去重（单次运行内） | 基于请求指纹的 dupefilter | 框架自带 |
| URL 去重（跨运行） | | `store.py` 里的 `known_source_ids`，在 `parse_listing` 中检查 |
| 监控 | stats 收集器 | `health.py` 里的 `HealthCheck`，结果写入 `crawl_runs` |
| 重抓策略 | | 翻到第一个没有新 id 的页就停；`PARSER_VERSION` |
| 内容去重 | Item Pipeline | `ContentDedupPipeline` |
| 校验 | Item Pipeline | `ValidatePipeline` |
| 存储 | Item Pipeline | `SQLitePipeline`，按 `url` 做 upsert |

## 目前的发现

**robots.txt 允许访问，不等于服务器放你进去。** 查了 35 家美国大公司，其中 19 个 IR 网站返回了 Cloudflare 的 JavaScript 挑战、Akamai 的拒绝页或者验证码，哪怕 robots.txt 写的是 `Allow: /`。其中 15 家的 robots.txt 一模一样，说明它们用的是同一个托管平台。本项目不尝试绕过反爬防护，这些网站不在范围内。

**Scrapy 不执行 `Crawl-delay`。** Scrapy 2.19 的 robots 解析器提供了 `crawl_delay()`，但框架里没有任何地方调用它。好几个 IR 网站设置了 `Crawl-delay: 10`。

只给 slot 设置一次间隔是不够的，有三样东西会把它改掉。AutoThrottle 每次收到响应都会重写间隔，唯一的下限是全局的 `DOWNLOAD_DELAY`。每个 slot 会加上 ±50% 的随机抖动。空闲约 60 秒的 slot 会被回收，重建时又回到默认间隔。`CrawlDelayAutoThrottle` 把这三种情况都处理了。

对一个设置了 `Crawl-delay: 3` 的本地网站，测量 5 次请求间隔：

| 限速方式 | 间隔（秒） | 低于 3 秒 |
|---|---|---|
| 原版 AutoThrottle，第 1 次 | 2.10, 2.24, 2.45, 2.99, 2.70 | 5 次中 4 次 |
| 原版 AutoThrottle，第 2 次 | 2.97, 2.96, 2.96, 2.51, 2.66 | 5 次中 2 次 |
| `CrawlDelayAutoThrottle`，2 次 | 每次都是 3.00 | 0 次 |

**Scrapy 重试 429 时不做退避。** `RetryMiddleware` 直接把请求放回队列，也不读 `Retry-After`。`RateLimitBackoffMiddleware` 会按 `Retry-After` 指定的时长暂停整个站点；没有这个头时按指数退避。重试次数用完，或者服务器要求等待的时间超过 `BACKOFF_MAX`，就放弃。

第一版在 `process_request` 里暂停请求，测试没通过：429 之后 0.2 秒，其他请求照样发了出去。原因是 Scrapy 已经把它们送过了中间件，放进了该站点的下载 slot 队列。现在暂停放在 `response_downloaded` 信号里做，Scrapy 在 slot 取下一个请求之前发出这个信号，做法是把 slot 的 `lastseen` 时间往后推。

对一个先返回一次 429（`Retry-After: 3`）、再提供 4 个页面的本地网站：

| 重试方式 | 429 之后多少秒发出 | 发得过早 |
|---|---|---|
| 原版 RetryMiddleware，第 1 次 | 0.29, 0.51, 0.76, 1.02 | 4 次中 4 次 |
| 原版 RetryMiddleware，第 2 次 | 0.17, 0.40, 0.68, 0.96 | 4 次中 4 次 |
| `RateLimitBackoffMiddleware`，第 1 次 | 3.30, 3.59, 3.86, 4.14 | 0 次 |
| `RateLimitBackoffMiddleware`，第 2 次 | 3.17, 3.43, 3.70, 3.92 | 0 次 |

**坏掉的爬虫照样正常结束。** 列表页被拦、选择器失效、提取时丢了文字，最后都显示 `finish_reason: finished`。而且在增量抓取下，0 条新数据也是正常运行该有的样子。所以 `HealthCheck` 从不靠数条数判断。每次运行结束后，它对每家公司检查：

| 检查项 | 能发现什么 | 规则 |
|---|---|---|
| `listing_not_reached` | 403、404、robots.txt 禁止 | 一个列表页都没解析到 |
| `listing_empty` | 列表页选择器失效 | 第 1 页没有链接 |
| `links_per_page_dropped` | 模板部分改动 | 每页链接数不到上次运行的一半 |
| `high_drop_rate` | 详情页模板改动 | 超过 20% 的详情页校验失败 |
| `low_coverage` | 提取逻辑有 bug | 正文保留的词数不到原文的 80% |

`low_coverage` 是因为下面那个表格 bug 才加的。原文词数特意和提取逻辑分开计算：如果两边用同一套节点选择，选择逻辑一出 bug，分子分母会一起变小，比例看起来还是正常的。在真实页面上：

| 页面 | 当前解析器 | 只读 `<p>` 的解析器 |
|---|---|---|
| AMD 2026 年 Q2 财报 | 1.00 | 0.26 |
| Intel 2026 年 Q2 财报 | 1.00 | 0.27 |
| AMD 董事任命公告 | 1.00 | 0.94 |

抓到的 44 篇 AMD 和 Intel 新闻稿，得分全部是 1.00。

`listing_empty` 第一版只要遇到空列表页就报警，测试没通过：翻过最后一页时本来就会遇到空页，这只是列表到头了。如果全量回填 AMD，在第 131 页也会触发同样的误报。现在只有第 1 页为空才算。

**同一个平台，不代表同一套模板。** AMD 和 Intel 用的是同一个 IR 平台，URL 结构和静态资源 CDN 都一样。第一次尝试直接拿 AMD 的列表页选择器去抓 Intel，结果一个链接都没找到。Intel 的主题用了不同的列表页结构，每条新闻链接了三次（图片、标题、按钮），文章里还多了一个相关文档框和一行 "Released" 日期。所以解析器按模板拆分，而不是按公司：抓取逻辑共用，每种模板只是 `LAYOUTS` 里的几个选择器。改完之后，AMD 已存的 20 行重新解析，内容 hash 完全一致，所以不需要升级 `PARSER_VERSION`。

这里有两件事，测试不能想当然。选择器写错不会报错：抓取正常结束，0 条数据，唯一的迹象是 `listing/empty` 这个统计值。另外，如果列表页选择器把每条新闻的三个链接全抓了，Scrapy 的 dupefilter 会把问题掩盖掉，因为每个 URL 仍然只抓一次。所以模板测试会检查 `dupefilter/filtered`。没有这个检查时，用错的选择器测试也能通过。

**增量抓取需要解析器版本号。** 再次运行时，会跳过网站 id 已经入库的新闻，并在第一个没有新 id 的列表页停止翻页。AMD 跑了两次：第一次发了 23 个请求，第二次只发了 2 个（robots.txt 和第 1 页）。

不在遇到第一条已知新闻时就停，是因为置顶或者改过日期的新闻可能排在新新闻上面。而且"已入库"指的是用当前 `PARSER_VERSION` 解析入库的。没有版本号的话，下面那个表格修复就永远作用不到修复之前存下的数据：那些行会被当成已完成，再也不会重新抓取。

**正文很长，也可能是错的。** 第一版解析器只读 `<p>` 标签。在 AMD 2026 年 Q2 财报上，它丢掉了 17 张表格和约 70% 的文字，所有净利润数字都没了。标题、日期、长度检查全部通过，没有任何报错。现在解析器按顺序读取每个块，并保留表格行。

## 已知问题

* 部分财务表格把 `$` 和数字拆在两个单元格里，行里会出现空格子。
* 公司在入库后修改了新闻稿，增量抓取发现不了。`-a full=1` 可以。
* 停止翻页的规则假设列表是按时间从新到旧排列的。
* `low_coverage` 的 80% 阈值发现不了小的丢失。只读 `<p>` 的解析器在一篇没有表格的新闻上丢了 6%，这种情况会通过检查。
* 健康检查结果只写进日志和 `crawl_runs` 表，还不会发告警，而且无论成败进程退出码都是 0。
* `links_per_page_dropped` 只和上一次运行比较。
* 退避状态存在下载 slot 里，所以只对单个爬虫进程有效。多个进程同时抓同一个站点，需要共享状态，比如 Redis。
* 空闲 slot 被回收再重建的情况，已通过写入下载器的 per-slot 设置处理，但还没有测试。测试需要空闲一分钟以上。

## 刻意不做的事

代理轮换、验证码破解、浏览器指纹伪装。这些是用来绕过那些主动选择屏蔽自动访问的网站的。
