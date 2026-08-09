# -*- coding: utf-8 -*-
"""AI HOT 日报抓取 —— 可复用 Python 模块

纯标准库实现，无第三方依赖，可直接 import 融入你的 agent：

    from aihot_daily import AihotDailyClient

    client = AihotDailyClient()
    report = client.get_latest()            # 最新日报（当日未生成自动回退最近一期）
    # report.get_by_date("2026-08-08")      # 指定日期
    data = report.to_dict()                 # 结构化 dict，可 JSON 序列化
"""
from .client import AihotDailyClient, DailyItem, DailyReport, DailySection
from . import render

__all__ = [
    "AihotDailyClient",
    "DailyItem",
    "DailySection",
    "DailyReport",
    "render",
]

__version__ = "1.0.0"
