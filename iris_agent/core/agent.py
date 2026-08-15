import json
import threading
from collections.abc import Iterator

from iris_agent.core.errors import ToolApprovalNotFoundError
from iris_agent.core.models import AgentEvent, Message, ToolCall
from iris_agent.memory.service import MemoryService
from iris_agent.tools.base import ToolExecutionResult
from iris_agent.providers.base import ModelProvider
from iris_agent.sessions.base import Session, SessionRepository
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
                if self.tools.requires_approval(call.name):
                    yield AgentEvent("tool_approval_requested", {
                        "call_id": call.id,
                        "name": call.name,
                        "arguments": call.arguments,
                        "context": self.tools.approval_context(call.name),
                    })
                    return
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
    def __init__(self, loop: AgentLoop, sessions: SessionRepository, system_prompt: str, memory: MemoryService | None = None):
        self.loop = loop
        self.sessions = sessions
        self.system_prompt = system_prompt
        self.memory = memory
        self._pending_approvals: dict[tuple[str, str], ToolCall] = {}
        self._approval_lock = threading.RLock()

    def _build_messages(self, session: Session) -> list[Message]:
        messages = [Message(role="system", content=self.system_prompt)]
        if self.memory is not None:
            for memory in self.memory.inject():
                messages.append(Message(role="system", content=f"[记忆·{memory.category}] {memory.content}"))
        messages.extend(session.messages)
        return messages

    def run(self, session_id: str, user_message: str) -> Iterator[AgentEvent]:
        with self.sessions.session_lock(session_id):
            self.sessions.append(session_id, Message(role="user", content=user_message))
            session = self.sessions.get(session_id)
            messages = self._build_messages(session)
            yield from self._run_loop(session_id, messages)

    def resolve_tool_approval(self, session_id: str, call_id: str, approved: bool) -> Iterator[AgentEvent]:
        with self.sessions.session_lock(session_id):
            with self._approval_lock:
                call = self._pending_approvals.pop((session_id, call_id), None)
            if call is None:
                raise ToolApprovalNotFoundError("待确认的工具调用不存在或已处理")
            if approved:
                result = self.loop.tools.invoke(call.name, call.arguments)
            else:
                result = ToolExecutionResult(False, error_code="tool_approval_rejected", error_message="用户拒绝执行此工具调用")
            event = self._tool_finished_event(call, result)
            self._persist_tool_result(session_id, event)
            yield event
            session = self.sessions.get(session_id)
            messages = self._build_messages(session)
            yield from self._run_loop(session_id, messages)

    def cancel_tool_approval(self, session_id: str, call_id: str) -> bool:
        """Discard a pending approval without invoking its tool."""
        with self._approval_lock:
            return self._pending_approvals.pop((session_id, call_id), None) is not None

    def _run_loop(self, session_id: str, messages: list[Message]) -> Iterator[AgentEvent]:
        for event in self.loop.run(messages):
            if event.type == "tool_started":
                call = ToolCall(str(event.data["call_id"]), str(event.data["name"]), dict(event.data.get("arguments", {})))
                self.sessions.append(session_id, Message(role="assistant", tool_calls=[call]))
            elif event.type == "tool_approval_requested":
                call = ToolCall(str(event.data["call_id"]), str(event.data["name"]), dict(event.data.get("arguments", {})))
                with self._approval_lock:
                    self._pending_approvals[(session_id, call.id)] = call
            elif event.type == "tool_finished":
                self._persist_tool_result(session_id, event)
            elif event.type == "message_completed":
                message = Message(role="assistant", content=str(event.data.get("content", "")))
                self.sessions.append(session_id, message)
                yield AgentEvent("message_completed", {"message_id": message.id})
                continue
            yield event

    @staticmethod
    def _tool_finished_event(call: ToolCall, result: ToolExecutionResult) -> AgentEvent:
        data = {"call_id": call.id, "name": call.name, "ok": result.ok}
        if result.ok:
            data["result"] = result.value
        else:
            data.update({"error_code": result.error_code, "error_message": result.error_message})
        return AgentEvent("tool_finished", data)

    def _persist_tool_result(self, session_id: str, event: AgentEvent) -> None:
        payload = event.data.get("result") if event.data.get("ok") else {"error": event.data.get("error_code"), "message": event.data.get("error_message")}
        self.sessions.append(session_id, Message(role="tool", content=json.dumps(payload, ensure_ascii=False), tool_call_id=str(event.data["call_id"]), name=str(event.data["name"])))
