import json
from collections.abc import Iterator

from iris_agent.core.models import AgentEvent, Message, ToolCall
from iris_agent.providers.base import ModelProvider
from iris_agent.sessions.base import SessionRepository
from iris_agent.tools.registry import ToolRegistry


class AgentLoop:
    def __init__(self, provider: ModelProvider, tools: ToolRegistry, max_tool_rounds: int = 8):
        self.provider = provider
        self.tools = tools
        self.max_tool_rounds = max_tool_rounds

    def run(self, messages: list[Message]) -> Iterator[AgentEvent]:
        working = list(messages)
        tool_rounds = 0
        while True:
            response = self.provider.complete(working, self.tools.schemas())
            if not response.tool_calls:
                if response.content:
                    yield AgentEvent("text_delta", {"content": response.content})
                yield AgentEvent("message_completed", {"content": response.content})
                return
            if tool_rounds >= self.max_tool_rounds:
                yield AgentEvent("error", {"code": "tool_round_limit", "message": "工具调用次数超过限制"})
                return
            tool_rounds += 1
            working.append(Message(role="assistant", content=response.content, tool_calls=response.tool_calls))
            for call in response.tool_calls:
                yield AgentEvent("tool_started", {"call_id": call.id, "name": call.name, "arguments": call.arguments})
                if call.argument_error:
                    from iris_agent.tools.base import ToolExecutionResult
                    result = ToolExecutionResult(False, error_code=call.argument_error, error_message="工具参数不是有效 JSON")
                else:
                    result = self.tools.invoke(call.name, call.arguments)
                data = {"call_id": call.id, "name": call.name, "ok": result.ok}
                if result.ok:
                    data["result"] = result.value
                else:
                    data.update({"error_code": result.error_code, "error_message": result.error_message})
                yield AgentEvent("tool_finished", data)
                content = json.dumps(result.value if result.ok else {"error": result.error_code, "message": result.error_message}, ensure_ascii=False)
                working.append(Message(role="tool", content=content, tool_call_id=call.id, name=call.name))


class AgentService:
    def __init__(self, loop: AgentLoop, sessions: SessionRepository, system_prompt: str):
        self.loop = loop
        self.sessions = sessions
        self.system_prompt = system_prompt

    def run(self, session_id: str, user_message: str) -> Iterator[AgentEvent]:
        with self.sessions.session_lock(session_id):
            self.sessions.append(session_id, Message(role="user", content=user_message))
            session = self.sessions.get(session_id)
            messages = [Message(role="system", content=self.system_prompt), *session.messages]
            for event in self.loop.run(messages):
                if event.type == "tool_started":
                    call = ToolCall(str(event.data["call_id"]), str(event.data["name"]), dict(event.data.get("arguments", {})))
                    self.sessions.append(session_id, Message(role="assistant", tool_calls=[call]))
                elif event.type == "tool_finished":
                    payload = event.data.get("result") if event.data.get("ok") else {"error": event.data.get("error_code"), "message": event.data.get("error_message")}
                    self.sessions.append(session_id, Message(role="tool", content=json.dumps(payload, ensure_ascii=False), tool_call_id=str(event.data["call_id"]), name=str(event.data["name"])))
                elif event.type == "message_completed":
                    message = Message(role="assistant", content=str(event.data.get("content", "")))
                    self.sessions.append(session_id, message)
                    yield AgentEvent("message_completed", {"message_id": message.id})
                    continue
                yield event
