# -*- coding: utf-8 -*-
"""世界时政热点抓取 —— 人民网国际 + 中新网国际

纯标准库（urllib + re + html.parser + concurrent.futures），零第三方依赖。
抓取两个国内可达的权威国际新闻频道列表页，解析标题 / 时间 / 链接，
再并行抓取详情页提取约 200 字正文摘要，去重合并后按时间倒序返回。

用法：
    from iris_agent.aihot_daily.world_news import WorldNewsClient
    items = WorldNewsClient().fetch()   # [{title, source, time, url, summary}, ...]
"""
import html as _html
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from iris_agent.aihot_daily.cache import daily_cached

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

SOURCES = [
    {
        "name": "人民网国际",
        "url": "http://world.people.com.cn/",
        "link_must_contain": "world.people.com.cn/n1/",
        "time_re": re.compile(r"/(\d{4})/(\d{2})(\d{2})/"),
        # 详情页正文容器起点（用于提取摘要）
        "detail_start": re.compile(r'<div class="layout rm_txt cf">', re.I),
    },
    {
        "name": "中新网国际",
        "url": "https://www.chinanews.com.cn/world/",
        "link_must_contain": "chinanews.com.cn/gj/",
        "time_re": re.compile(r"/(\d{4})/(\d{2})-(\d{2})/"),
        "detail_start": re.compile(r'<div class="content" id="cont_1_1_2">', re.I),
    },
]

MAX_ITEMS = 24
SUMMARY_LEN = 200
DETAIL_TIMEOUT = 10
DETAIL_WORKERS = 6


class WorldNewsError(RuntimeError):
    """时政数据不可用时的统一异常"""


def _fetch_html(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        raise WorldNewsError(f"抓取失败 {url}: {e}")


def _extract_date_from_url(url, time_re):
    """从 URL 中提取发布日期；解析不到返回 None"""
    m = time_re.search(url)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def _clean_title(raw):
    """清洗标题：去 HTML 标签/实体、取首行、压缩空白、限制长度"""
    t = re.sub(r"<[^>]+>", "", raw)
    t = _html.unescape(t)
    t = t.split("\n")[0].strip()
    t = re.sub(r"\s+", " ", t).strip()
    return t[:60]


def _parse_page(html_text, source):
    """从列表页 HTML 提取 (title, url, date) 去重后的列表"""
    items = []
    seen_urls, seen_titles = set(), set()
    pattern = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S)
    for m in pattern.finditer(html_text):
        url = m.group(1).strip()
        if url.startswith("//"):  # 协议相对地址补全为 https
            url = "https:" + url
        if source["link_must_contain"] not in url:
            continue
        title = _clean_title(m.group(2))
        if len(title) < 8 or any(ch in title for ch in ("查看更多", "频道首页", "返回顶部")):
            continue
        if url in seen_urls or title in seen_titles:
            continue
        seen_urls.add(url)
        seen_titles.add(title)
        date = _extract_date_from_url(url, source["time_re"])
        items.append({"title": title, "url": url, "date": date})
    return items


def _plain_text(html_text):
    """去 script/style/标签，压缩空白，返回纯文本"""
    t = re.sub(r"<script.*?</script>", "", html_text, flags=re.S)
    t = re.sub(r"<style.*?</style>", "", t, flags=re.S)
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    t = re.sub(r"<[^>]+>", "", t)
    t = _html.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _truncate_sentence(text, maxlen):
    """在 maxlen 字内尽量于句号/感叹号处截断，返回 ≤maxlen 字摘要"""
    if len(text) <= maxlen:
        return text
    cut = text[:maxlen]
    # 优先在句子边界断
    for sep in ("。", "！", "？", "；"):
        idx = cut.rfind(sep)
        if idx >= maxlen * 0.5:
            return cut[: idx + 1]
    return cut.rstrip("，,、 ") + "…"


def _fetch_detail_summary(url, source):
    """抓取详情页并提取约 200 字正文摘要；失败返回空串"""
    try:
        html_text = _fetch_html(url, timeout=DETAIL_TIMEOUT)
    except WorldNewsError:
        return ""
    start = source.get("detail_start")
    if start:
        m = start.search(html_text)
        if m:
            html_text = html_text[m.start():]
    # 只取正文容器内的 <p> 段落（跳过标题/时间/来源等元信息）
    paragraphs = [_plain_text(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", html_text, re.S)]
    paragraphs = [p for p in paragraphs if len(p) >= 20]
    text = "".join(paragraphs) if paragraphs else _plain_text(html_text)
    return _truncate_sentence(text, SUMMARY_LEN)


class WorldNewsClient:
    """世界时政热点抓取客户端"""

    def __init__(self, max_items=MAX_ITEMS, timeout=15, with_summary=True):
        self.max_items = max_items
        self.timeout = timeout
        self.with_summary = with_summary

    def fetch(self):
        """抓取并合并全部源，按时间倒序，返回 [{title, source, time, url, summary}]

        结果按北京时间当天缓存：当天内重复调用直接返回缓存，跨天自动重新抓取。
        """
        return self._fetch_impl()

    @daily_cached
    def _fetch_impl(self):
        merged = []
        for src in SOURCES:
            try:
                html_text = _fetch_html(src["url"], timeout=self.timeout)
                for it in _parse_page(html_text, src):
                    merged.append({
                        "title": it["title"],
                        "url": it["url"],
                        "time": it["date"].strftime("%Y-%m-%d") if it["date"] else "",
                        "source": src["name"],
                        "summary": "",
                    })
            except WorldNewsError:
                continue  # 单个源失败不影响整体

        if not merged:
            raise WorldNewsError("所有时政源均抓取失败")

        merged.sort(key=lambda x: x["time"], reverse=True)
        merged = merged[: self.max_items]

        # 并行抓详情页摘要
        if self.with_summary:
            source_by_url = {}
            for src in SOURCES:
                source_by_url[src["name"]] = src
            with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as pool:
                futures = []
                for it in merged:
                    src = source_by_url.get(it["source"])
                    if src:
                        futures.append((it, pool.submit(_fetch_detail_summary, it["url"], src)))
                for it, fut in futures:
                    try:
                        it["summary"] = fut.result(timeout=DETAIL_TIMEOUT + 2)
                    except Exception:
                        it["summary"] = ""

        return merged
