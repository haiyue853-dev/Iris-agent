from __future__ import annotations


_DOMAIN_EXPANSIONS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("网断", "网络中断", "断线", "重新连", "重连"),
     ("流式返回", "网络中断", "前端重连", "恢复上下文", "断点续传", "避免重复输出", "丢包")),
    (("删掉", "删除", "旧答案", "旧知识", "脏召回", "脏数据"),
     ("文档删除", "向量库实时一致性", "旧知识", "脏数据", "检索滞后", "增量更新")),
    (("不沾边", "无关片段", "跑偏", "瞎答"),
     ("无关片段", "检索相关性", "相似度阈值", "混合检索", "重排序")),
    (("一大坨日志", "日志量", "冷热数据", "留痕审计"),
     ("日志存储", "日志检索", "审计", "冷热分层", "降冷")),
    (("好几个版本", "多个版本", "重复版本", "水文", "低质量文档"),
     ("噪声文档", "无效文档", "重复文档", "文档去重", "过滤")),
    (("特别慢", "长尾", "很吃资源", "吃资源"),
     ("长尾任务", "资源消耗", "任务隔离", "性能优化", "成本控制")),
    (("十几秒", "一直挂着", "完成通知", "失败重跑"),
     ("异步任务", "任务状态管理", "重试机制", "结果通知", "持久化")),
)


def expand_retrieval_query(query: str) -> str:
    """Append bounded domain terms for colloquial RAG queries without replacing intent."""
    if not isinstance(query, str) or not query.strip():
        return query
    additions: list[str] = []
    for triggers, terms in _DOMAIN_EXPANSIONS:
        if any(trigger.casefold() in query.casefold() for trigger in triggers):
            additions.extend(term for term in terms if term.casefold() not in query.casefold())
    unique = list(dict.fromkeys(additions))
    return f"{query} {' '.join(unique)}" if unique else query
