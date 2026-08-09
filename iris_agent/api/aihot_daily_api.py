"""AI HOT 每日日报 API 路由（资讯日报，独立于工作日报助手）

对应设计文档「后续路线」中的热点总结助手雏形：拉取 AI HOT 每日 AI 圈资讯日报。

接口（统一挂在 /api/aihot-daily 前缀下）：
  GET /api/aihot-daily/latest          → 最新一期（当日未生成自动回退最近一期）
  GET /api/aihot-daily/{date}          → 指定日期（未生成自动回退，is_fallback=true）
  GET /api/aihot-daily/{date}/markdown → Markdown 简报
  GET /api/aihot-daily/{date}/html     → 单文件 HTML 晨报（网页/iframe 嵌入）
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from iris_agent.aihot_daily import AihotDailyClient, render
from iris_agent.aihot_daily.client import AihotError

router = APIRouter(prefix="/api/aihot-daily", tags=["aihot-daily"])
client = AihotDailyClient()


@router.get("/latest")
def get_latest():
    """最新一期日报；当日尚未生成自动回退最近一期"""
    try:
        return client.get_latest().to_dict()
    except AihotError as exc:
        raise HTTPException(status_code=502, detail={"code": "aihot_daily_unavailable", "message": exc.safe_message if hasattr(exc, "safe_message") else str(exc)})


@router.get("/{date}")
def get_by_date(date: str):
    """指定日期（YYYY-MM-DD）；该日未生成自动回退，is_fallback=true"""
    try:
        return client.get_by_date(date).to_dict()
    except AihotError as exc:
        raise HTTPException(status_code=404, detail={"code": "aihot_daily_not_found", "message": str(exc)})


@router.get("/{date}/markdown")
def get_markdown(date: str, with_summary: bool = True):
    """Markdown 简报（agent 对话 / 复制用）"""
    try:
        report = client.get_by_date(date)
        return {
            "date": report.date,
            "is_fallback": report.is_fallback,
            "fallback_from": report.fallback_from,
            "markdown": render.to_markdown(report, with_summary=with_summary),
        }
    except AihotError as exc:
        raise HTTPException(status_code=404, detail={"code": "aihot_daily_not_found", "message": str(exc)})


@router.get("/{date}/html", response_class=HTMLResponse)
def get_html(date: str):
    """单文件 HTML 晨报（淡黄+白 / SVG 图标）"""
    try:
        report = client.get_by_date(date)
        return render.to_html(report)
    except AihotError as exc:
        raise HTTPException(status_code=404, detail={"code": "aihot_daily_not_found", "message": str(exc)})
