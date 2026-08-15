"""Knowledge tools: add entries and search the knowledge base."""

from iris_agent.knowledge.service import KnowledgeService
from iris_agent.tools.base import Tool, ToolInvocationError


def build_add_knowledge_tool(service: KnowledgeService) -> Tool:
    def add_knowledge(title: str, content: str, category: str = "面经", source_url: str | None = None):
        try:
            entry = service.add(title, content, category=category, source_url=source_url)
        except ValueError as exc:
            raise ToolInvocationError("invalid_knowledge", str(exc)) from exc
        return {
            "id": entry.id,
            "title": entry.title,
            "category": entry.category,
            "source_type": entry.source_type,
        }

    return Tool(
        "add_knowledge",
        "保存一条知识到知识库（如面试经验、面经、教程）",
        {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "条目标题"},
                "content": {"type": "string", "description": "条目正文内容"},
                "category": {"type": "string", "description": "分类，默认「面经」"},
                "source_url": {"type": "string", "description": "来源链接（可选）"},
            },
            "required": ["title", "content"],
        },
        add_knowledge,
        requires_approval=False,
    )


def build_search_knowledge_tool(service: KnowledgeService) -> Tool:
    def search_knowledge(query: str, limit: int | None = None):
        hits = service.search(query, limit)
        return {"hits": [hit.to_dict() for hit in hits]}

    return Tool(
        "search_knowledge",
        "检索知识库，返回与查询相关的内容片段",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "要搜索的关键词或问题"},
                "limit": {"type": "integer", "description": "返回条数上限"},
            },
            "required": ["query"],
        },
        search_knowledge,
        requires_approval=False,
    )
