from dataclasses import asdict

from fastapi import APIRouter, HTTPException, status

from iris_agent.notifications.service import NotificationService


def register_notification_routes(app, notifications: NotificationService) -> None:
    router = APIRouter(prefix="/api/notifications", tags=["notifications"])

    @router.get("")
    def list_notifications():
        return {"notifications": [asdict(item) for item in notifications.list_notifications()]}

    @router.put("/{notification_id}/read")
    def mark_read(notification_id: str):
        try:
            return asdict(notifications.mark_read(notification_id))
        except KeyError:
            raise HTTPException(404, detail={"code": "notification_not_found", "message": "通知不存在"})

    @router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete(notification_id: str):
        try:
            notifications.delete(notification_id)
        except KeyError:
            raise HTTPException(404, detail={"code": "notification_not_found", "message": "通知不存在"})

    app.include_router(router)
