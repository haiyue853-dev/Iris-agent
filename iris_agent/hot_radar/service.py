from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import uuid4


Source = Callable[[], list[dict[str, object]]]


@dataclass(frozen=True, slots=True)
class RadarSubscription:
    id: str
    keyword: str


@dataclass(frozen=True, slots=True)
class RadarItem:
    id: str
    title: str
    url: str
    source: str
    summary: str
    keyword: str


@dataclass(frozen=True, slots=True)
class ScanResult:
    new_count: int
    failed_sources: tuple[str, ...]

    @property
    def summary(self) -> str:
        failed = f"；{len(self.failed_sources)} 个来源不可用" if self.failed_sources else ""
        return f"新增 {self.new_count} 条热点{failed}"


class HotRadarService:
    def __init__(self, root: Path, sources: dict[str, Source] | None = None):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = root / "radar.json"
        self.sources = sources or self._default_sources()

    @staticmethod
    def _default_sources() -> dict[str, Source]:
        from iris_agent.aihot_daily.tech_news import TechNewsClient
        from iris_agent.aihot_daily.world_news import WorldNewsClient
        return {"tech": lambda: TechNewsClient().fetch(), "world": lambda: WorldNewsClient().fetch()}

    def _read(self) -> dict[str, list[dict[str, str]]]:
        if not self.path.exists(): return {"subscriptions": [], "items": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, list[dict[str, str]]]) -> None:
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        temp.replace(self.path)

    def list_subscriptions(self) -> list[RadarSubscription]:
        return [RadarSubscription(**raw) for raw in self._read()["subscriptions"]]

    def create_subscription(self, keyword: str) -> RadarSubscription:
        clean = keyword.strip()
        if not clean: raise ValueError("关键词不能为空")
        data = self._read()
        if any(item["keyword"] == clean for item in data["subscriptions"]): raise ValueError("关键词已订阅")
        subscription = RadarSubscription(uuid4().hex, clean)
        data["subscriptions"].append({"id": subscription.id, "keyword": subscription.keyword})
        self._write(data)
        return subscription

    def list_items(self) -> list[RadarItem]:
        return [RadarItem(**raw) for raw in self._read()["items"]]

    def scan(self) -> ScanResult:
        data = self._read(); keywords = [item["keyword"] for item in data["subscriptions"]]
        seen = {item["id"] for item in data["items"]}; failed: list[str] = []; added = 0
        for name, fetch in self.sources.items():
            try: candidates = fetch()
            except Exception: failed.append(name); continue
            for raw in candidates:
                title, summary, url = str(raw.get("title", "")), str(raw.get("summary", "")), str(raw.get("url", ""))
                keyword = next((word for word in keywords if word.casefold() in f"{title}\n{summary}".casefold()), None)
                if not keyword: continue
                item_id = hashlib.sha256((url or title).encode("utf-8")).hexdigest()[:24]
                if item_id in seen: continue
                seen.add(item_id); added += 1
                data["items"].append({"id": item_id, "title": title, "url": url, "source": str(raw.get("source", name)), "summary": summary[:500], "keyword": keyword})
        self._write(data)
        return ScanResult(added, tuple(failed))
