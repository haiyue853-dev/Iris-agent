"""世界时政热点 API 路由（独立于 AI 日报）

数据源：人民网国际 + 中新网国际（国内可达的权威国际新闻频道）
接口：
  GET /api/world-news/latest → 时政热点列表 [{title, source, time, url}, ...]
"""

from fastapi import APIRouter, HTTPException

from iris_agent.aihot_daily.world_news import WorldNewsClient, WorldNewsError

router = APIRouter(prefix="/api/world-news", tags=["world-news"])
client = WorldNewsClient()


@router.get("/latest")
def get_latest():
    """世界时政热点（按时间倒序，最多 24 条）"""
    try:
        items = client.fetch()
        return {"count": len(items), "items": items}
    except WorldNewsError as exc:
        raise HTTPException(status_code=502, detail={"code": "world_news_unavailable", "message": str(exc)})
