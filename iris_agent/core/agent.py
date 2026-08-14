import json
import threading
from collections.abc import Iterator
from dataclasses import replace

from iris_agent.core.context import ContextEngine
from iris_agent.memory.service import MemoryService
from iris_agent.core.errors import ToolApprovalNotFoundError
from iris_agent.core.models import AgentEvent, Message, ToolCall
from iris_agent.tools.base import ToolExecutionResult
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
        attempts: dict[str, int] = {}
        while True:
            response = self.provider.complete(working, self.tools.schemas())
            if not response.tool_calls:
                if response.content:
                    yield AgentEvent("react_step", {
                        "phase": "final",
                        "content": response.content,
                    })
                    yield AgentEvent("text_delta", {"content": response.content})
                yield AgentEvent("message_completed", {"content": response.content})
                return
            if tool_rounds >= self.max_tool_rounds:
                yield AgentEvent("error", {"code": "tool_round_limit", "message": "工具调用次数超过限制"})
                return
            tool_rounds += 1
            if response.content:
                yield AgentEvent("react_step", {
                    "phase": "thought",
                    "content": response.content,
                    "round": tool_rounds,
                })
            working.append(Message(role="assistant", content=response.content, tool_calls=response.tool_calls))
            for call in response.tool_calls:
                signature = self._call_signature(call)
                attempts[signature] = attempts.get(signature, 0) + 1
                yield AgentEvent("react_step", {
                    "phase": "action",
                    "call_id": call.id,
                    "name": call.name,
                    "arguments": call.arguments,
                    "round": tool_rounds,
                    "attempt": attempts[signature],
                    "retry": attempts[signature] > 1,
                })
                yield AgentEvent("tool_started", {"call_id": call.id, "name": call.name, "arguments": call.arguments})
                if self.tools.requires_approval(call.name):
                    yield AgentEvent("tool_approval_requested", {
                        "call_id": call.id,
                        "name": call.name,
                        "arguments": call.arguments,
                        "context": self.tools.approval_context(call.name),
                    })
                    return
                if attempts[signature] > 2:
                    result = ToolExecutionResult(
                        False,
                        error_code="repeated_tool_call",
                        error_message="Repeated identical call; choose a different source, query, or tool.",
                    )
                elif call.argument_error:
                    result = ToolExecutionResult(False, error_code=call.argument_error, error_message="工具参数不是有效 JSON")
                else:
                    result = self.tools.invoke(call.name, call.arguments)
                data = {"call_id": call.id, "name": call.name, "ok": result.ok}
                if result.ok:
                    data["result"] = result.value
                else:
                    data.update({"error_code": result.error_code, "error_message": result.error_message})
                yield AgentEvent("tool_finished", data)
                yield self._observation_event(call, result, tool_rounds)
                content = json.dumps(result.value if result.ok else {"error": result.error_code, "message": result.error_message}, ensure_ascii=False)
                working.append(Message(role="tool", content=content, tool_call_id=call.id, name=call.name))

    @staticmethod
    def _call_signature(call: ToolCall) -> str:
        """Stable signature used to prevent an identical failed tool call from looping forever."""
        arguments = json.dumps(call.arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return f"{call.name}:{arguments}"

    @staticmethod
    def _observation_event(call: ToolCall, result: ToolExecutionResult, round_number: int | None = None) -> AgentEvent:
        data = {"phase": "observation", "call_id": call.id, "name": call.name, "ok": result.ok}
        if round_number is not None:
            data["round"] = round_number
        if result.ok:
            data["result"] = result.value
        else:
            data.update({"error_code": result.error_code, "error_message": result.error_message})
        return AgentEvent("react_step", data)


class AgentService:
    def __init__(self, loop: AgentLoop, sessions: SessionRepository, system_prompt: str, context: ContextEngine | None = None, memory: MemoryService | None = None):
        self.loop = loop
        self.sessions = sessions
        self.system_prompt = system_prompt
        self.context = context
        self.memory = memory
        self._pending_approvals: dict[tuple[str, str], ToolCall] = {}
        self._approval_lock = threading.RLock()

    def run(self, session_id: str, user_message: str, skill_instructions: str | None = None) -> Iterator[AgentEvent]:
        with self.sessions.session_lock(session_id):
            self.sessions.append(session_id, Message(role="user", content=user_message))
            session = self.sessions.get(session_id)
            messages = self._messages(session_id, session.messages, skill_instructions)
            yield from self._run_loop(session_id, messages)

    def resolve_tool_approval(self, session_id: str, call_id: str, approved: bool, skill_instructions: str | None = None) -> Iterator[AgentEvent]:
        with self.sessions.session_lock(session_id):
            with self._approval_lock:
                call = self._pending_approvals.pop((session_id, call_id), None)
            if call is None:
                call = self._restore_pending_call(session_id, call_id)
            if call is None:
                raise ToolApprovalNotFoundError("待确认的工具调用不存在或已处理")
            if approved:
                result = self.loop.tools.invoke(call.name, call.arguments)
            else:
                result = ToolExecutionResult(False, error_code="tool_approval_rejected", error_message="用户拒绝执行此工具调用")
            event = self._tool_finished_event(call, result)
            self._persist_tool_result(session_id, event)
            yield event
            yield self.loop._observation_event(call, result)
            session = self.sessions.get(session_id)
            messages = self._messages(session_id, session.messages, skill_instructions)
            yield from self._run_loop(session_id, messages)

    def _messages(self, session_id: str, history: list[Message], skill_instructions: str | None) -> list[Message]:
        messages = self.context.build(session_id, self.system_prompt, history) if self.context else [Message(role="system", content=self.system_prompt), *history]
        additions = []
        if skill_instructions:
            additions.append(f"Use this active Skill for the current request:\n{skill_instructions}")
        if self.memory:
            latest_user = next((message.content for message in reversed(history) if message.role == "user"), "")
            memory_context = self.memory.context_for(latest_user, session_id)
            if memory_context:
                additions.append(memory_context)
        if not additions:
            return messages
        additions_text = "\n\n".join(additions)
        for index in range(len(messages) - 1, 0, -1):
            if messages[index].role == "user":
                messages[index] = replace(messages[index], content=f"{messages[index].content}\n\n{additions_text}")
                return messages
        messages.append(Message(role="user", content=additions_text))
        return messages

    def cancel_tool_approval(self, session_id: str, call_id: str) -> bool:
        """Discard a pending approval without invoking its tool."""
        with self.sessions.session_lock(session_id):
            with self._approval_lock:
                call = self._pending_approvals.pop((session_id, call_id), None)
            if call is None:
                call = self._restore_pending_call(session_id, call_id)
            if call is None:
                return False
            cancelled = ToolExecutionResult(
                False,
                error_code="tool_approval_cancelled",
                error_message="工具调用已取消",
            )
            self._persist_tool_result(session_id, self._tool_finished_event(call, cancelled))
            return True

    def _restore_pending_call(self, session_id: str, call_id: str) -> ToolCall | None:
        """Recover an approval request from durable conversation history after a restart."""
        session = self.sessions.get(session_id)
        completed = {message.tool_call_id for message in session.messages if message.role == "tool" and message.tool_call_id}
        if call_id in completed:
            return None
        for message in reversed(session.messages):
            for call in message.tool_calls:
                if call.id == call_id and self.loop.tools.requires_approval(call.name):
                    return call
        return None

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
