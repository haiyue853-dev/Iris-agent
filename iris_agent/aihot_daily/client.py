# -*- coding: utf-8 -*-
"""AI HOT 日报抓取核心：数据模型 + 客户端

功能：
- get_latest()          最新一期日报；最新一期 404 时自动回退到最近一期
- get_by_date(date)     指定日期；该日期 404（当日尚未生成）自动回退最近一期，并标记 is_fallback
- 时间统一转北京时间人话格式；原始数据保留在 report.raw

纯标准库（urllib），无第三方依赖，方便嵌入任意 Python agent。
"""
import json
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

API_BASE = "https://aihot.virxact.com/api/v1"
USER_AGENT = "aihot-daily-agent/1.0 (+https://aihot.virxact.com/aihot-skill/)"
BJ = timezone(timedelta(hours=8))
WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


class AihotError(RuntimeError):
    """AI HOT 数据不可用时的统一异常"""


@dataclass
class DailyItem:
    """单条日报资讯"""
    no: int
    title: str
    summary: str
    source: str
    url_original: str          # 第三方原文链接（可能为空）
    url_aihot: str             # AI HOT 站内阅读页
    section: str = ""          # 所属版块标签
    category: str = ""         # 原始分类（可能为空）

    def to_dict(self):
        return {
            "no": self.no,
            "title": self.title,
            "summary": self.summary,
            "source": self.source,
            "url_original": self.url_original,
            "url_aihot": self.url_aihot,
            "section": self.section,
        }

    @property
    def url(self):
        """推荐跳转链接：优先原文，无原文则站内页"""
        return self.url_original or self.url_aihot


@dataclass
class DailySection:
    """日报版块（模型/产品/行业/论文/技巧）"""
    label: str
    items: list = field(default_factory=list)

    @property
    def count(self):
        return len(self.items)

    def to_dict(self):
        return {"label": self.label, "count": self.count,
                "items": [it.to_dict() for it in self.items]}


@dataclass
class DailyReport:
    """一期完整日报"""
    date: str                  # 2026-08-08
    date_human: str            # 2026年8月8日 · 星期六
    generated_at: str          # 北京时间人话格式
    total: int
    sections: list = field(default_factory=list)
    daily_url: str = ""        # AI HOT 日报站内页
    is_fallback: bool = False  # True = 目标日期未生成，回退到了最近一期
    fallback_from: str = ""    # 回退前的目标日期
    raw: dict = field(default_factory=dict)  # API 原始响应

    def to_dict(self):
        """结构化输出，可直接 json.dumps 传给 agent / LLM"""
        return {
            "date": self.date,
            "date_human": self.date_human,
            "generated_at": self.generated_at,
            "total": self.total,
            "is_fallback": self.is_fallback,
            "fallback_from": self.fallback_from,
            "daily_url": self.daily_url,
            "sections": [s.to_dict() for s in self.sections],
        }


class AihotDailyClient:
    """AI HOT 日报抓取客户端"""

    def __init__(self, api_base=API_BASE, user_agent=USER_AGENT, timeout=30):
        self.api_base = api_base.rstrip("/")
        self.user_agent = user_agent
        self.timeout = timeout

    # ---------- HTTP ----------
    def _http_get(self, path):
        """匿名只读 GET，返回 (status, body_str)。404 也返回而不抛异常。"""
        url = f"{self.api_base}{path}"
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", errors="replace")
        except Exception as e:  # 网络错误等
            return -1, str(e)

    def _get_json(self, path):
        status, body = self._http_get(path)
        if status != 200:
            raise AihotError(f"AI HOT 请求失败 {path} (HTTP {status})")
        return json.loads(body)

    def _fetch_index(self):
        """日报索引（最近 7 期），返回列表；失败返回空"""
        try:
            idx = self._get_json("/dailies?limit=7")
            return idx.get("items") or []
        except AihotError:
            return []

    # ---------- 对外 API ----------
    def get_latest(self):
        """最新一期日报；最新不可用（404）时回退到索引中最近一期。

        返回 DailyReport；数据不可用时抛 AihotError。
        """
        try:
            data = self._get_json("/dailies/latest")
            return self._parse(data, is_fallback=False)
        except AihotError:
            # 回退：查索引取最近日期
            items = self._fetch_index()
            if items:
                date = items[0].get("date")
                if date:
                    data = self._get_json(f"/dailies/{date}")
                    return self._parse(data, is_fallback=True, fallback_from=date)
            raise AihotError("AI HOT 当前没有可用日报（latest 与索引均失败）")

    def get_by_date(self, date):
        """指定日期日报；该日期不存在（当日尚未生成）时自动回退最近一期。

        返回 DailyReport（is_fallback=True 表示发生了回退）。
        """
        try:
            data = self._get_json(f"/dailies/{date}")
            return self._parse(data, is_fallback=False)
        except AihotError:
            # 回退到最近一期
            items = self._fetch_index()
            if items:
                fallback = items[0].get("date")
                if fallback:
                    data = self._get_json(f"/dailies/{fallback}")
                    return self._parse(data, is_fallback=True, fallback_from=date)
            raise AihotError(f"AI HOT 日报 {date} 不存在，且无可用回退（HTTP 404）")

    # ---------- 解析 ----------
    def _parse(self, data, is_fallback=False, fallback_from=""):
        report = data.get("report") or data
        date_str = report["date"]

        d = datetime.strptime(date_str, "%Y-%m-%d")
        date_human = f"{d.year}年{d.month}月{d.day}日 · {WEEKDAYS[d.weekday()]}"

        gen_dt = datetime.fromisoformat(report["generatedAt"].replace("Z", "+00:00")).astimezone(BJ)
        gen_human = f"{gen_dt.year}年{gen_dt.month}月{gen_dt.day}日 {gen_dt:%H:%M}（北京时间）"

        sections = []
        global_no = 0
        for s in report.get("sections") or []:
            label = s.get("label", "未分类")
            items = []
            for it in s.get("items") or []:
                global_no += 1
                links = it.get("links") or {}
                src_obj = it.get("source") or {}
                source = src_obj.get("name", "未知来源") if isinstance(src_obj, dict) else str(src_obj or "未知来源")
                items.append(DailyItem(
                    no=global_no,
                    title=it.get("title", ""),
                    summary=(it.get("summary") or "").strip(),
                    source=source,
                    url_original=links.get("original") or "",
                    url_aihot=links.get("aihot") or "",
                    section=label,
                    category=it.get("category") or "",
                ))
            sections.append(DailySection(label=label, items=items))

        daily_url = (report.get("links") or {}).get("aihot", "") or f"https://aihot.virxact.com/daily/{date_str}"
        total = sum(s.count for s in sections)

        return DailyReport(
            date=date_str,
            date_human=date_human,
            generated_at=gen_human,
            total=total,
            sections=sections,
            daily_url=daily_url,
            is_fallback=is_fallback,
            fallback_from=fallback_from,
            raw=data,
        )
