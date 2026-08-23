"""Web search result model."""

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
import re
from typing import Any


_DOMAIN_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


def _normalize_domains(domains, field: str) -> tuple[str, ...]:
    values = tuple(domains)
    if len(values) > 20:
        raise ValueError(f"{field} must contain at most 20 domains")

    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            raise ValueError(f"{field} entries must be domain strings")
        if len(value) > 253:
            raise ValueError(f"{field} entries must contain at most 253 characters")
        domain = value.strip().lower()
        if not domain:
            raise ValueError(f"{field} entries must contain 1 to 253 characters")
        try:
            ascii_domain = domain.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError(f"{field} contains an invalid IDN domain") from exc
        if len(ascii_domain) > 253:
            raise ValueError(f"{field} entries must contain at most 253 ASCII characters")
        try:
            ip_address(ascii_domain)
        except ValueError:
            pass
        else:
            raise ValueError(f"{field} must not contain IP addresses")
        labels = ascii_domain.split(".")
        if any(_DOMAIN_LABEL.fullmatch(label) is None for label in labels):
            raise ValueError(f"{field} entries must be plain domains")
        if ascii_domain not in seen:
            seen.add(ascii_domain)
            normalized.append(ascii_domain)
    return tuple(normalized)


@dataclass(slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str | None = None
    published_date: str | None = None
    score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
        }
        for field in ("source", "published_date", "score"):
            value = getattr(self, field)
            if value is not None:
                result[field] = value
        return result


@dataclass(frozen=True, slots=True)
class SearchOptions:
    topic: str = "general"
    time_range: str | None = None
    include_domains: tuple[str, ...] = ()
    exclude_domains: tuple[str, ...] = ()
    search_depth: str = "basic"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "include_domains",
            _normalize_domains(self.include_domains, "include_domains"),
        )
        object.__setattr__(
            self,
            "exclude_domains",
            _normalize_domains(self.exclude_domains, "exclude_domains"),
        )
        if self.topic not in {"general", "news"}:
            raise ValueError("topic must be 'general' or 'news'")
        if self.time_range not in {None, "day", "week", "month", "year"}:
            raise ValueError("time_range must be None, 'day', 'week', 'month', or 'year'")
        if self.search_depth not in {"basic", "advanced"}:
            raise ValueError("search_depth must be 'basic' or 'advanced'")
