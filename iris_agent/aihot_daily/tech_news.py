# -*- coding: utf-8 -*-
"""计算机行业新闻抓取 —— IT之家 + 网易科技

纯标准库（urllib + re + html + concurrent.futures），零第三方依赖。
抓取两个国内可达的计算机/IT 行业新闻源首页，用关键词过滤聚焦
「计算机行业」（芯片/软硬件/系统/云计算/互联网公司/AI 产业等），
再并行抓取详情页提取约 200 字摘要与发布时间。

用法：
    from iris_agent.aihot_daily.tech_news import TechNewsClient
    items = TechNewsClient().fetch()   # [{title, source, time, url, summary}, ...]
"""
import html as _html
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from iris_agent.aihot_daily.cache import daily_cached

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

# 计算机行业关键词（标题命中任一即保留）
COMPUTER_KEYWORDS = (
    "芯片", "半导体", "晶圆", "处理器", "CPU", "GPU", "内存", "存储", "固态", "SSD",
    "显卡", "服务器", "数据中心", "云计算", "操作系统", "Windows", "Linux", "macOS",
    "鸿蒙", "安卓", "iOS", "软件", "硬件", "开发者", "开源", "编程", "数据库",
    "英伟达", "NVIDIA", "AMD", "英特尔", "Intel", "高通", "苹果", "Apple", "微软",
    "谷歌", "Google", "OpenAI", "Anthropic", "Meta", "腾讯", "阿里", "字节", "百度",
    "华为", "小米", "AI", "人工智能", "大模型", "机器人", "智能体", "自动驾驶",
    "量子", "光刻", "5G", "6G", "Wi-Fi", "蓝牙", "车机", "智能座舱", "鸿蒙座舱",
    "电商", "互联网", "App", "应用", "浏览器", "搜索引擎", "网络安全", "编程语言",
    "Rust", "Python", "Java", "Go", "TypeScript", "大模型", "智算", "算力", "GPU集群",
)

# 明确排除的标题关键词（非计算机行业）
EXCLUDE_KEYWORDS = (
    "新能源汽车", "汽车上市", "试驾", "比亚迪海豹", "SUV", "轿车", "车型", "上市：",
    "小米汽车", "答网友问", "智能电动门", "汽车发布",
    "电影", "电视剧", "综艺", "明星", "游戏评测", "PS5", "Switch", "足球", "NBA",
    "楼市", "房产", "股票", "基金", "茅台", "白酒", "减肥", "健身", "餐饮",
    "除草剂", "农民", "养殖", "庄稼", "小麦", "水稻",
)


class TechNewsError(RuntimeError):
    """计算机行业新闻不可用时的统一异常"""


def _fetch_html(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        raise TechNewsError(f"抓取失败 {url}: {e}")


def _clean_title(raw):
    t = re.sub(r"<[^>]+>", "", raw)
    t = _html.unescape(t)
    t = t.split("\n")[0].strip()
    t = re.sub(r"\s+", " ", t).strip()
    return t[:80]


def _is_computer_news(title):
    """标题命中计算机关键词且未命中排除词则保留"""
    if any(k in title for k in EXCLUDE_KEYWORDS):
        return False
    return any(k in title for k in COMPUTER_KEYWORDS)


def _plain_text(html_text):
    t = re.sub(r"<script.*?</script>", "", html_text, flags=re.S)
    t = re.sub(r"<style.*?</style>", "", t, flags=re.S)
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    t = re.sub(r"<[^>]+>", "", t)
    t = _html.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _truncate_sentence(text, maxlen):
    if len(text) <= maxlen:
        return text
    cut = text[:maxlen]
    for sep in ("。", "！", "？", "；"):
        idx = cut.rfind(sep)
        if idx >= maxlen * 0.5:
            return cut[: idx + 1]
    return cut.rstrip("，,、 ") + "…"


def _extract_time(html_text):
    """从详情页提取发布时间 YYYY-MM-DD；失败返回空串"""
    # 匹配 2026年8月8日 / 2026-08-08 / 2026/08/08
    for pat in (
        re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日"),
        re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})"),
        re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})"),
    ):
        m = pat.search(html_text)
        if m:
            try:
                return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            except ValueError:
                continue
    return ""


def _fetch_detail(url):
    """抓详情页，返回 (summary, time)；失败返回 ("", "")"""
    try:
        html_text = _fetch_html(url, timeout=10)
    except TechNewsError:
        return "", ""
    paragraphs = [_plain_text(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", html_text, re.S)]
    paragraphs = [p for p in paragraphs if len(p) >= 20]
    summary = _truncate_sentence("".join(paragraphs), 200) if paragraphs else ""
    return summary, _extract_time(html_text)


# ---------------- 各源解析 ----------------
def _parse_ithome(html_text):
    """IT之家首页：href 形如 https://www.ithome.com/0/xxx/xxx.htm"""
    items = []
    seen_urls, seen_titles = set(), set()
    for m in re.finditer(r'<a[^>]+href="(https://www\.ithome\.com/0/\d+/\d+\.htm)"[^>]*>(.*?)</a>', html_text, re.S):
        url = m.group(1).strip()
        if url.startswith("//"):
            url = "https:" + url
        title = _clean_title(m.group(2))
        if len(title) < 10 or not _is_computer_news(title):
            continue
        if url in seen_urls or title in seen_titles:
            continue
        seen_urls.add(url)
        seen_titles.add(title)
        items.append({"title": title, "url": url})
    return items


def _parse_163(html_text):
    """网易科技首页：href 形如 https://www.163.com/tech/article/xxx.html 或 dy/article"""
    items = []
    seen_urls, seen_titles = set(), set()
    for m in re.finditer(r'<a[^>]+href="(https://(?:www\.163\.com/tech|www\.163\.com/dy)/article/[^"]+\.html)"[^>]*>(.*?)</a>', html_text, re.S):
        url = m.group(1).strip()
        if url.startswith("//"):
            url = "https:" + url
        title = _clean_title(m.group(2))
        if len(title) < 10 or not _is_computer_news(title):
            continue
        if url in seen_urls or title in seen_titles:
            continue
        seen_urls.add(url)
        seen_titles.add(title)
        items.append({"title": title, "url": url})
    return items


class TechNewsClient:
    """计算机行业新闻抓取客户端"""

    def __init__(self, max_items=16, timeout=15, with_summary=True):
        self.max_items = max_items
        self.timeout = timeout
        self.with_summary = with_summary

    def fetch(self):
        """抓取并合并 IT之家 + 网易科技，返回 [{title, source, time, url, summary}]

        结果按北京时间当天缓存：当天内重复调用直接返回缓存，跨天自动重新抓取。
        """
        return self._fetch_impl()

    @daily_cached
    def _fetch_impl(self):
        merged = []
        sources = [
            ("IT之家", "https://www.ithome.com/", _parse_ithome),
            ("网易科技", "https://tech.163.com/", _parse_163),
        ]
        for name, url, parser in sources:
            try:
                html_text = _fetch_html(url, timeout=self.timeout)
                for it in parser(html_text):
                    merged.append({
                        "title": it["title"],
                        "url": it["url"],
                        "time": "",
                        "source": name,
                        "summary": "",
                    })
            except TechNewsError:
                continue

        if not merged:
            raise TechNewsError("所有计算机行业源均抓取失败")

        # 并行抓详情（摘要 + 时间）
        if self.with_summary:
            with ThreadPoolExecutor(max_workers=6) as pool:
                futures = [(it, pool.submit(_fetch_detail, it["url"])) for it in merged]
                for it, fut in futures:
                    try:
                        summary, time = fut.result(timeout=12)
                        it["summary"] = summary
                        it["time"] = time
                    except Exception:
                        it["summary"] = ""
                        it["time"] = ""

        # 按时间倒序（无时间的排后面）
        merged.sort(key=lambda x: x["time"], reverse=True)
        return merged[: self.max_items]
