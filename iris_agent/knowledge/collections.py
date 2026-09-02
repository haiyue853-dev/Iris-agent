"""Models for isolated local knowledge collections."""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from typing import Mapping
from uuid import uuid4

_COLLECTION_ID = re.compile(r"^collection-[0-9a-f]{32}$|^collection-general$")
_RETRIEVAL_CONFIG_FIELDS = frozenset({
    "top_k", "candidate_multiplier", "minimum_relevance_score", "mmr_relevance_weight",
})


def normalise_retrieval_config(config: Mapping[str, object] | None) -> dict[str, int | float]:
    if config is None:
        return {}
    if not isinstance(config, Mapping) or not set(config).issubset(_RETRIEVAL_CONFIG_FIELDS):
        raise ValueError("invalid knowledge collection retrieval config")
    normalised: dict[str, int | float] = {}
    for key, value in config.items():
        if key in {"top_k", "candidate_multiplier"}:
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= (20 if key == "top_k" else 10):
                raise ValueError(f"invalid {key}")
        elif not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"invalid {key}")
        normalised[key] = value
    return normalised


@dataclass(frozen=True, slots=True)
class KnowledgeCollection:
    id: str
    name: str
    description: str | None
    created_at: float
    retrieval_config: dict[str, int | float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not _COLLECTION_ID.fullmatch(self.id):
            raise ValueError("invalid knowledge collection id")
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 80:
            raise ValueError("knowledge collection name must be 1-80 characters")
        if self.description is not None and (not isinstance(self.description, str) or len(self.description) > 300):
            raise ValueError("invalid knowledge collection description")
        if not isinstance(self.created_at, (int, float)) or isinstance(self.created_at, bool) or not math.isfinite(self.created_at):
            raise ValueError("invalid knowledge collection timestamp")
        object.__setattr__(self, "retrieval_config", normalise_retrieval_config(self.retrieval_config))

    @classmethod
    def new(cls, name: str, description: str | None = None) -> "KnowledgeCollection":
        return cls(f"collection-{uuid4().hex}", name.strip(), description.strip() if description else None, time.time())

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "description": self.description, "created_at": self.created_at,
                "retrieval_config": dict(self.retrieval_config)}
