from typing import Protocol

from iris_agent.core.models import Message, ProviderResponse


class ModelProvider(Protocol):
    def complete(self, messages: list[Message], tools: list[dict]) -> ProviderResponse: ...
