"""Recall tool: search historical sessions and return matching fragments."""

from iris_agent.session_search.service import SessionSearchService
from iris_agent.tools.base import Tool


def build_recall_tool(search: SessionSearchService) -> Tool:
    def recall(query: str):
        hits = search.search(query)
        return {"hits": [hit.to_dict() for hit in hits]}

    return Tool(
        "recall",
        "搜索历史会话，召回与查询相关的内容片段",
        {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "要搜索的关键词或问题"}},
            "required": ["query"],
        },
        recall,
        requires_approval=False,
    )
