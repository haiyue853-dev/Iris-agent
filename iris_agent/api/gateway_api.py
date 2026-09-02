"""HTTP controls used by the message channels page."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from iris_agent.gateway.qq import QQOneBotAdapter
from iris_agent.gateway.napcat import NapCatError, NapCatLauncher


class QQTestMessage(BaseModel):
    user_id: str
    text: str = "Iris QQ 连接测试"


class NapCatPathRequest(BaseModel):
    path: str


class NapCatDirectoryRequest(BaseModel):
    directory: str


def register_gateway_routes(app, qq_adapter: QQOneBotAdapter | None, qq_ws_path: str, napcat: NapCatLauncher | None = None) -> None:
    router = APIRouter(prefix="/api/gateway", tags=["gateway"])

    @router.get("/channels")
    def list_channels():
        return {
            "channels": [{
                "id": "qq",
                "name": "QQ",
                "enabled": qq_adapter is not None,
                "connected": bool(qq_adapter is not None and qq_adapter.connected),
                "transport": "OneBot 11 反向 WebSocket",
                "websocket_path": qq_ws_path,
            }]
        }

    @router.post("/qq/test")
    def send_qq_test_message(request: QQTestMessage):
        user_id = request.user_id.strip()
        text = request.text.strip()
        if not user_id.isdigit() or not text:
            raise HTTPException(422, detail={"code": "invalid_qq_test_message", "message": "请输入有效的 QQ 号和测试内容"})
        if qq_adapter is None or not qq_adapter.connected:
            raise HTTPException(409, detail={"code": "qq_not_connected", "message": "QQ 客户端尚未连接 Iris"})
        if not qq_adapter.push_text(user_id, text):
            raise HTTPException(503, detail={"code": "qq_send_failed", "message": "QQ 测试消息发送失败"})
        return {"ok": True}

    @router.get("/napcat")
    def get_napcat_status():
        return napcat.status() if napcat is not None else {"path": "", "configured": False, "running": False}

    @router.put("/napcat")
    def save_napcat_path(request: NapCatPathRequest):
        if napcat is None:
            raise HTTPException(503, detail={"code": "napcat_unavailable", "message": "NapCat 启动功能不可用"})
        try:
            return napcat.save_path(request.path)
        except NapCatError as exc:
            raise HTTPException(422, detail={"code": exc.code, "message": exc.message}) from exc

    @router.post("/napcat/open")
    def open_napcat():
        if napcat is None:
            raise HTTPException(503, detail={"code": "napcat_unavailable", "message": "NapCat 启动功能不可用"})
        try:
            return napcat.launch()
        except NapCatError as exc:
            status_code = 409 if exc.code == "napcat_not_configured" else 503
            raise HTTPException(status_code, detail={"code": exc.code, "message": exc.message}) from exc

    @router.post("/napcat/match")
    def match_napcat_directory(request: NapCatDirectoryRequest):
        if napcat is None:
            raise HTTPException(503, detail={"code": "napcat_unavailable", "message": "NapCat 启动功能不可用"})
        try:
            return napcat.match_directory(request.directory)
        except NapCatError as exc:
            raise HTTPException(422, detail={"code": exc.code, "message": exc.message}) from exc

    app.include_router(router)
