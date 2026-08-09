"""计算机行业新闻 API 路由

数据源：IT之家 + 网易科技（关键词过滤聚焦计算机行业）
接口：
  GET /api/tech-news/latest → 计算机行业新闻列表 [{title, source, time, url, summary}, ...]
"""

from fastapi import APIRouter, HTTPException

from iris_agent.aihot_daily.tech_news import TechNewsClient, TechNewsError

router = APIRouter(prefix="/api/tech-news", tags=["tech-news"])
client = TechNewsClient()


@router.get("/latest")
def get_latest():
    """计算机行业新闻（按时间倒序，最多 16 条，含 200 字摘要）"""
    try:
        items = client.fetch()
        return {"count": len(items), "items": items}
    except TechNewsError as exc:
        raise HTTPException(status_code=502, detail={"code": "tech_news_unavailable", "message": str(exc)})
