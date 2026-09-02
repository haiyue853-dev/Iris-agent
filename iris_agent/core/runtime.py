from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Iterable


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(parts: Iterable[str]) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SessionRuntimeSnapshot:
    epoch: int
    model: str | None
    system_messages: tuple[str, ...]
    tool_names: tuple[str, ...]
    tool_schema_json: tuple[str, ...]
    tool_schema_hash: str
    prefix_hash: str
    created_at: float

    @classmethod
    def create(cls, *, epoch: int, model: str | None, system_messages: tuple[str, ...], tool_schemas: tuple[dict[str, Any], ...], created_at: float | None = None) -> "SessionRuntimeSnapshot":
        schema_json = tuple(_canonical(schema) for schema in tool_schemas)
        names = tuple(str(schema.get("function", {}).get("name", "")) for schema in tool_schemas)
        schema_hash = _digest(schema_json)
        prefix_hash = _digest((str(epoch), model or "", *system_messages, schema_hash))
        return cls(epoch, model, system_messages, names, schema_json, schema_hash, prefix_hash, created_at or time.time())

    def to_dict(self) -> dict[str, Any]:
        return {"epoch": self.epoch, "model": self.model, "system_messages": list(self.system_messages), "tool_schemas": [json.loads(item) for item in self.tool_schema_json], "tool_schema_hash": self.tool_schema_hash, "prefix_hash": self.prefix_hash, "created_at": self.created_at}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SessionRuntimeSnapshot":
        schemas = raw.get("tool_schemas")
        if schemas is None:
            schemas = [json.loads(item) for item in raw.get("tool_schema_json", ())]
        return cls.create(epoch=int(raw.get("epoch", 1)), model=raw.get("model"), system_messages=tuple(str(item) for item in raw.get("system_messages", ())), tool_schemas=tuple(schemas), created_at=float(raw.get("created_at", time.time())))
