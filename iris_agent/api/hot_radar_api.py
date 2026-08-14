from dataclasses import asdict

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from iris_agent.hot_radar.service import HotRadarService


class SubscriptionRequest(BaseModel):
    keyword: str = Field(min_length=1, max_length=80)


def register_hot_radar_routes(app, radar: HotRadarService) -> None:
    router = APIRouter(prefix="/api/hot-radar", tags=["hot-radar"])
    @router.get("/subscriptions")
    def subscriptions(): return {"subscriptions": [asdict(item) for item in radar.list_subscriptions()]}
    @router.post("/subscriptions", status_code=status.HTTP_201_CREATED)
    def create(request: SubscriptionRequest):
        try: item = radar.create_subscription(request.keyword)
        except ValueError as exc: raise HTTPException(422, detail={"code": "hot_radar_validation", "message": str(exc)})
        return {"id": item.id, "keyword": item.keyword}
    @router.delete("/subscriptions/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete(subscription_id: str):
        try: radar.delete_subscription(subscription_id)
        except KeyError: raise HTTPException(404, detail={"code": "hot_radar_not_found", "message": "订阅不存在"})
    @router.get("/items")
    def items(): return {"items": [asdict(item) for item in radar.list_items()]}
    @router.post("/scan")
    def scan():
        result = radar.scan()
        return {"new_count": result.new_count, "failed_sources": result.failed_sources, "summary": result.summary}
    app.include_router(router)
