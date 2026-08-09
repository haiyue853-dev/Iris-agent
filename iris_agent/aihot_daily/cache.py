# -*- coding: utf-8 -*-
"""按天缓存工具

在 iris_agent / aihot_daily 中使用：当天第一次调用执行原函数并缓存结果，
之后同一天内的任何调用直接返回缓存（不再重复抓取外部数据源），
跨天（北京时间）自动失效并重新执行。

仅缓存成功结果：函数抛异常时不缓存，下次调用会重试。
"""
import functools
from datetime import datetime, timezone, timedelta

BJ = timezone(timedelta(hours=8))


def daily_cached(func):
    """装饰器：按北京时间当天缓存函数返回值"""
    state: dict = {"date": None, "value": None}

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        today = datetime.now(BJ).strftime("%Y-%m-%d")
        if state["date"] == today and state["value"] is not None:
            return state["value"]
        value = func(*args, **kwargs)
        state["date"] = today
        state["value"] = value
        return value

    return wrapper
