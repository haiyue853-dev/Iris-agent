import json
import threading
from contextlib import nullcontext
from collections.abc import Callable, Iterator
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from iris_agent.core.errors import ToolApprovalNotFoundError
from iris_agent.core.models import AgentEvent, Message, ProviderResponse, ToolCall
from iris_agent.context_compression.compressor import ContextCompressor
from iris_agent.memory.service import MemoryService
from iris_agent.profile.service import ProfileService
from iris_agent.tools.base import ToolExecutionResult
from iris_agent.providers.base import ModelProvider
from iris_agent.sessions.base import Session, SessionRepository
from iris_agent.tools.registry import ToolRegistry
from iris_agent.attachments.service import AttachmentService


class AgentLoop:
    def __init__(self, provider: ModelProvider, tools: ToolRegistry, max_tool_rounds: int = 8):
        self._provider = provider
        self._provider_lock = threading.RLock()
        self.tools = tools
        self.max_tool_rounds = max_tool_rounds

    @property
    def provider(self) -> ModelProvider:
        return self.get_provider()

    def get_provider(self) -> ModelProvider:
        with self._provider_lock:
            return self._provider

    def replace_provider(self, provider: ModelProvider) -> None:
        with self._provider_lock:
            self._provider = provider

    def run(self, messages: list[Message], tools: ToolRegistry | None = None, is_cancelled: Callable[[], bool] | None = None) -> Iterator[AgentEvent]:
        with self._provider_lock:
            provider = self._provider
        lease = getattr(provider, "lease", None)
        context = lease() if callable(lease) else nullcontext(provider)
        with context as request_provider:
            yield from self._run_with_provider(request_provider, messages, tools, is_cancelled)

    def _run_with_provider(self, provider: ModelProvider, messages: list[Message], tools: ToolRegistry | None = None, is_cancelled: Callable[[], bool] | None = None) -> Iterator[AgentEvent]:
        registry = tools or self.tools
        cancelled = is_cancelled or (lambda: False)
        working = list(messages)
        tool_rounds = 0
        while True:
            if cancelled():
                return
            stream = getattr(provider, "stream", None)
            if callable(stream):
                content_parts: list[str] = []
                tool_calls: list[ToolCall] = []
                for chunk in stream(working, registry.schemas()):
                    if cancelled():
                        return
                    if chunk.content:
                        content_parts.append(chunk.content)
                        yield AgentEvent("text_delta", {"content": chunk.content})
                    if chunk.tool_calls:
                        tool_calls = chunk.tool_calls
                response = ProviderResponse("".join(content_parts), tool_calls)
            else:
                response = provider.complete(working, registry.schemas())
            if not response.tool_calls:
                if response.content and not callable(stream):
                    yield AgentEvent("text_delta", {"content": response.content})
                yield AgentEvent("message_completed", {"content": response.content})
                return
            if tool_rounds >= self.max_tool_rounds:
                yield AgentEvent("error", {"code": "tool_round_limit", "message": "工具调用次数超过限制"})
                return
            tool_rounds += 1
            working.append(Message(role="assistant", content=response.content, tool_calls=response.tool_calls))
            call_index = 0
            while call_index < len(response.tool_calls):
                call = response.tool_calls[call_index]
                fetch_batch: list[ToolCall] = []
                while (
                    call_index < len(response.tool_calls)
                    and response.tool_calls[call_index].name == "fetch_page"
                    and not response.tool_calls[call_index].argument_error
                    and not registry.requires_approval("fetch_page")
                ):
                    fetch_batch.append(response.tool_calls[call_index])
                    call_index += 1
                if len(fetch_batch) >= 2:
                    for fetch_call in fetch_batch:
                        yield AgentEvent("tool_started", {"call_id": fetch_call.id, "name": fetch_call.name, "arguments": fetch_call.arguments})
                    executor = ThreadPoolExecutor(max_workers=min(3, len(fetch_batch)), thread_name_prefix="iris-fetch")
                    futures = [executor.submit(registry.invoke, fetch_call.name, fetch_call.arguments) for fetch_call in fetch_batch]
                    pending = set(futures)
                    while pending:
                        if cancelled():
                            for future in pending:
                                future.cancel()
                            executor.shutdown(wait=False, cancel_futures=True)
                            return
                        _, pending = wait(pending, timeout=0.05, return_when=FIRST_COMPLETED)
                    executor.shutdown(wait=True)
                    if cancelled():
                        return
                    for fetch_call, future in zip(fetch_batch, futures):
                        result = future.result()
                        data = {"call_id": fetch_call.id, "name": fetch_call.name, "ok": result.ok}
                        if result.ok:
                            data["result"] = result.value
                        else:
                            data.update({"error_code": result.error_code, "error_message": result.error_message})
                        yield AgentEvent("tool_finished", data)
                        content = json.dumps(result.value if result.ok else {"error": result.error_code, "message": result.error_message}, ensure_ascii=False)
                        working.append(Message(role="tool", content=content, tool_call_id=fetch_call.id, name=fetch_call.name))
                    continue
                if fetch_batch:
                    call = fetch_batch[0]
                else:
                    call_index += 1
                if cancelled():
                    return
                yield AgentEvent("tool_started", {"call_id": call.id, "name": call.name, "arguments": call.arguments})
                if registry.requires_approval(call.name):
                    yield AgentEvent("tool_approval_requested", {
                        "call_id": call.id,
                        "name": call.name,
                        "arguments": call.arguments,
                        "context": registry.approval_context(call.name),
                    })
                    return
                if call.argument_error:
                    from iris_agent.tools.base import ToolExecutionResult
                    result = ToolExecutionResult(False, error_code=call.argument_error, error_message="工具参数不是有效 JSON")
                else:
                    result = registry.invoke(call.name, call.arguments)
                if cancelled():
                    return
                data = {"call_id": call.id, "name": call.name, "ok": result.ok}
                if result.ok:
                    data["result"] = result.value
                else:
                    data.update({"error_code": result.error_code, "error_message": result.error_message})
                yield AgentEvent("tool_finished", data)
                content = json.dumps(result.value if result.ok else {"error": result.error_code, "message": result.error_message}, ensure_ascii=False)
                working.append(Message(role="tool", content=content, tool_call_id=call.id, name=call.name))


class AgentService:
    def __init__(self, loop: AgentLoop, sessions: SessionRepository, system_prompt: str, memory: MemoryService | None = None, profile_service: ProfileService | None = None, compressor: ContextCompressor | None = None, attachment_service: AttachmentService | None = None):
        self.loop = loop
        self.sessions = sessions
        self.system_prompt = system_prompt
        self.memory = memory
        self.profile_service = profile_service
        self.compressor = compressor
        self.attachment_service = attachment_service
        self._pending_approvals: dict[tuple[str, str], tuple[ToolCall, ToolRegistry, Callable[[], bool]]] = {}
        self._approval_lock = threading.RLock()

    def _build_messages(self, session: Session) -> list[Message]:
        if self.compressor is not None and self.compressor.needs_compression(session.messages):
            session.messages = self.compressor.compress(session.messages)
            self.sessions.save(session)
        messages = [Message(role="system", content=self.system_prompt)]
        if self.profile_service is not None:
            profile_text = self.profile_service.render()
            if profile_text:
                messages.append(Message(role="system", content=profile_text))
        if self.memory is not None:
            for memory in self.memory.inject():
                messages.append(Message(role="system", content=f"[记忆·{memory.category}] {memory.content}"))
        for message in session.messages:
            if message.attachment_ids and self.attachment_service is not None:
                details = []
                for attachment_id in message.attachment_ids:
                    try:
                        item = self.attachment_service.read(session.id, attachment_id)
                        details.append(f"- {item.original_name} (attachment_id: {attachment_id}; 提取状态: {item.extraction_status}; 来源: {', '.join(item.sources) or '无'})")
                    except Exception:
                        details.append(f"- {attachment_id} (附件信息不可用)")
                enriched = Message(role=message.role, content=message.content + "\n\n[当前消息附件]\n" + "\n".join(details) + "\n如需读取附件内容，必须先调用 read_attachment，并使用对应的 attachment_id。", tool_calls=message.tool_calls, tool_call_id=message.tool_call_id, name=message.name, attachment_ids=list(message.attachment_ids), id=message.id)
                messages.append(enriched)
            else:
                messages.append(message)
        return messages

    def run(self, session_id: str, user_message: str, attachment_ids: list[str] | None = None, is_cancelled: Callable[[], bool] | None = None) -> Iterator[AgentEvent]:
        with self.sessions.session_lock(session_id):
            self.sessions.append(session_id, Message(role="user", content=user_message, attachment_ids=list(attachment_ids or [])))
            session = self.sessions.get(session_id)
            messages = self._build_messages(session)
            yield from self._run_loop(session_id, messages, self._registry_for(session_id), is_cancelled)
            if self.profile_service is not None:
                self.profile_service.maybe_update(user_message)

    def resolve_tool_approval(self, session_id: str, call_id: str, approved: bool) -> Iterator[AgentEvent]:
        with self.sessions.session_lock(session_id):
            with self._approval_lock:
                pending = self._pending_approvals.pop((session_id, call_id), None)
            if pending is None:
                raise ToolApprovalNotFoundError("待确认的工具调用不存在或已处理")
            call, registry, is_cancelled = pending
            if is_cancelled():
                return
            if approved:
                result = registry.invoke(call.name, call.arguments)
            else:
                result = ToolExecutionResult(False, error_code="tool_approval_rejected", error_message="用户拒绝执行此工具调用")
            if is_cancelled():
                return
            event = self._tool_finished_event(call, result)
            self._persist_tool_result(session_id, event)
            yield event
            session = self.sessions.get(session_id)
            messages = self._build_messages(session)
            yield from self._run_loop(session_id, messages, registry, is_cancelled)

    def cancel_tool_approval(self, session_id: str, call_id: str) -> bool:
        """Discard a pending approval without invoking its tool."""
        with self._approval_lock:
            return self._pending_approvals.pop((session_id, call_id), None) is not None

    def _registry_for(self, session_id: str) -> ToolRegistry:
        registry = self.loop.tools.copy()
        if self.attachment_service is not None:
            from iris_agent.tools.builtin.attachments import build_read_attachment_tool
            registry.register(build_read_attachment_tool(self.attachment_service, session_id))
        return registry

    def _run_loop(self, session_id: str, messages: list[Message], registry: ToolRegistry, is_cancelled: Callable[[], bool] | None = None) -> Iterator[AgentEvent]:
        cancelled = is_cancelled or (lambda: False)
        for event in self.loop.run(messages, registry, cancelled):
            if event.type == "tool_started":
                call = ToolCall(str(event.data["call_id"]), str(event.data["name"]), dict(event.data.get("arguments", {})))
                self.sessions.append(session_id, Message(role="assistant", tool_calls=[call]))
            elif event.type == "tool_approval_requested":
                call = ToolCall(str(event.data["call_id"]), str(event.data["name"]), dict(event.data.get("arguments", {})))
                with self._approval_lock:
                    self._pending_approvals[(session_id, call.id)] = (call, registry, cancelled)
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
