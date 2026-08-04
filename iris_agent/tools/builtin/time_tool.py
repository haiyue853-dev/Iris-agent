from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from iris_agent.tools.base import Tool, ToolInvocationError


def build_current_time_tool(default_timezone: str = "Asia/Shanghai") -> Tool:
    def current_time(timezone: str = default_timezone):
        try:
            now = datetime.now(ZoneInfo(timezone))
        except ZoneInfoNotFoundError as exc:
            raise ToolInvocationError("invalid_timezone", f"未知时区: {timezone}") from exc
        return {"timezone": timezone, "iso": now.isoformat()}

    return Tool("current_time", "获取指定时区的当前时间", {"type": "object", "properties": {"timezone": {"type": "string"}}}, current_time)
