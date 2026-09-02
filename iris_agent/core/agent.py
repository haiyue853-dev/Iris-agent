import json
import base64
import re
import threading
from time import monotonic
from contextlib import nullcontext
from collections.abc import Callable, Iterator
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from iris_agent.core.errors import ToolApprovalNotFoundError, ValidationError
from iris_agent.core.models import AgentEvent, Message, ProviderResponse, ToolCall
from iris_agent.core.runtime import SessionRuntimeSnapshot
from iris_agent.context_compression.compressor import ContextCompressor
from iris_agent.memory.service import MemoryService
from iris_agent.profile.service import ProfileService
from iris_agent.tools.base import ToolExecutionResult
from iris_agent.providers.base import ModelProvider
from iris_agent.sessions.base import Session, SessionRepository
from iris_agent.tools.capabilities import CapabilityResolver
from iris_agent.tools.registry import ToolRegistry
from iris_agent.attachments.service import AttachmentService


class AgentLoop:
    # These lookup tools return a complete snapshot for the current request.
    # Re-offering them after one use makes smaller models repeatedly query the
    # same source instead of composing an answer from the result already in
    # their context, adding a full model round-trip each time.
    _ONE_SHOT_LOOKUP_TOOLS = frozenset({"web_search", "search_knowledge", "recall", "current_time", "request_subagent_collaboration"})

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

    def execute_tool_call(self, call: ToolCall, registry: ToolRegistry, cancelled: Callable[[], bool]) -> Iterator[AgentEvent]:
        """Execute one tool and forward optional incremental progress events."""
        if call.argument_error:
            result = ToolExecutionResult(False, error_code=call.argument_error, error_message="工具参数不是有效 JSON")
        else:
            result = registry.invoke(call.name, call.arguments)
            stream = getattr(result.value, "stream", None) if result.ok else None
            if callable(stream):
                execution = result.value
                for progress in stream():
                    yield AgentEvent("tool_progress", {"call_id": call.id, "name": call.name, **dict(progress)})
                    if cancelled():
                        cancel = getattr(execution, "cancel", None)
                        if callable(cancel): cancel()
                result = ToolExecutionResult(True, value=getattr(execution, "result", None))
            elif cancelled():
                return
        data = {"call_id": call.id, "name": call.name, "ok": result.ok}
        if result.ok: data["result"] = result.value
        else: data.update({"error_code": result.error_code, "error_message": result.error_message})
        yield AgentEvent("tool_finished", data)

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
        used_one_shot_lookups: set[str] = set()
        finalization_requested = False
        forced_tool_call_attempts = 0
        while True:
            if cancelled():
                return
            model_started_at = monotonic()
            first_token_at: float | None = None
            if tool_rounds >= self.max_tool_rounds:
                if not finalization_requested:
                    working.append(Message(role="system", content="工具预算已用完。只能基于已有工具结果直接给出最终结论；不得再调用工具，也不要描述过程。"))
                    finalization_requested = True
                available_tool_schemas = []
            else:
                available_tool_schemas = [
                    schema
                    for schema in registry.schemas()
                    if schema.get("function", {}).get("name") not in used_one_shot_lookups
                ]
            stream = getattr(provider, "stream", None)
            if callable(stream):
                content_parts: list[str] = []
                tool_calls: list[ToolCall] = []
                for chunk in stream(working, available_tool_schemas):
                    if cancelled():
                        return
                    if chunk.content:
                        first_token_at = first_token_at or monotonic()
                        content_parts.append(chunk.content)
                        yield AgentEvent("text_delta", {"content": chunk.content})
                    if chunk.tool_calls:
                        tool_calls = chunk.tool_calls
                response = ProviderResponse("".join(content_parts), tool_calls)
            else:
                response = provider.complete(working, available_tool_schemas)
            if not response.tool_calls:
                if response.content and not callable(stream):
                    yield AgentEvent("text_delta", {"content": response.content})
                completed_at = monotonic()
                yield AgentEvent("message_completed", {"content": response.content, "metrics": {"first_token_ms": None if first_token_at is None else round((first_token_at - model_started_at) * 1000), "duration_ms": round((completed_at - model_started_at) * 1000), "model": getattr(provider, "model", None)}})
                return
            if finalization_requested:
                forced_tool_call_attempts += 1
                if forced_tool_call_attempts >= 2:
                    completed_at = monotonic()
                    yield AgentEvent("message_completed", {"content": response.content or "已根据已获取的信息完成处理。", "metrics": {"first_token_ms": None if first_token_at is None else round((first_token_at - model_started_at) * 1000), "duration_ms": round((completed_at - model_started_at) * 1000), "model": getattr(provider, "model", None)}})
                    return
                working.append(Message(role="assistant", content=response.content))
                continue
            tool_rounds += 1
            used_one_shot_lookups.update(
                call.name for call in response.tool_calls if call.name in self._ONE_SHOT_LOOKUP_TOOLS
            )
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
                final_data: dict | None = None
                for tool_event in self.execute_tool_call(call, registry, cancelled):
                    yield tool_event
                    if tool_event.type == "tool_finished": final_data = tool_event.data
                if final_data is None: return
                content = json.dumps(final_data.get("result") if final_data.get("ok") else {"error": final_data.get("error_code"), "message": final_data.get("error_message")}, ensure_ascii=False)
                working.append(Message(role="tool", content=content, tool_call_id=call.id, name=call.name))
                if cancelled(): return


class AgentService:
    def __init__(self, loop: AgentLoop, sessions: SessionRepository, system_prompt: str, memory: MemoryService | None = None, profile_service: ProfileService | None = None, compressor: ContextCompressor | None = None, attachment_service: AttachmentService | None = None, knowledge=None, vision_enabled: bool = False, capability_resolver: CapabilityResolver | None = None, knowledge_orchestrator=None, model_profile_resolver: Callable[[str], ModelProvider | None] | None = None):
        self.loop = loop
        self.sessions = sessions
        self.system_prompt = system_prompt
        self.memory = memory
        self.profile_service = profile_service
        self.compressor = compressor
        self.attachment_service = attachment_service
        self.knowledge = knowledge
        self.knowledge_orchestrator = knowledge_orchestrator
        self.vision_enabled = vision_enabled
        self.capability_resolver = capability_resolver
        self.model_profile_resolver = model_profile_resolver
        self.delegation_service = None
        self._pending_approvals: dict[tuple[str, str], tuple[ToolCall, ToolRegistry, Callable[[], bool], list[dict], ModelProvider, bool]] = {}
        self._approval_lock = threading.RLock()

    def optimize_prompt(self, draft: str, instruction: str) -> str:
        response = self.loop.get_provider().complete(
            [Message(role="system", content=instruction), Message(role="user", content=draft)],
            [],
        )
        return response.content.strip() or draft

    def _ensure_runtime_snapshot(self, session: Session, registry: ToolRegistry, provider: ModelProvider | None = None) -> SessionRuntimeSnapshot:
        if session.runtime_snapshot is not None:
            return session.runtime_snapshot
        system_messages = [self.system_prompt]
        if self.profile_service is not None:
            profile_text = self.profile_service.render()
            if profile_text:
                system_messages.append(profile_text)
        if self.memory is not None:
            for memory in self.memory.inject():
                system_messages.append(f"[记忆·{memory.category}] {memory.content}")
        provider = provider or self.loop.get_provider()
        session.runtime_snapshot = SessionRuntimeSnapshot.create(
            epoch=1,
            model=getattr(provider, "model", None),
            system_messages=tuple(system_messages),
            tool_schemas=tuple(registry.schemas()),
        )
        self.sessions.save(session)
        return session.runtime_snapshot

    def _provider_for_session(self, session: Session) -> tuple[ModelProvider, bool]:
        if session.model_profile_id and self.model_profile_resolver is not None:
            provider = self.model_profile_resolver(session.model_profile_id)
            if provider is not None:
                return provider, True
            session.model_profile_id = None
            self.sessions.save(session)
        return self.loop.get_provider(), False

    def _turn_prompt(self, session_id: str, user_message: str, attachment_ids: list[str], response_mode: str, knowledge_collection_id: str | None, knowledge_query_mode: str, knowledge_enabled: bool, citations: list[dict], skill_name: str | None = None, skill_instruction: str | None = None) -> str:
        mode_instruction = "[本轮模式] 快速模式：优先直接、简洁回答，仅在确有必要时调用工具。" if response_mode == "fast" else "[本轮模式] 思考模式：充分分析，必要时调用工具核实。"
        parts = [user_message, mode_instruction]
        if self._is_fast_interview_collection_request(user_message):
            parts.append("[快速面经入库模式] 只能调用 collect_interview_knowledge 一次。不要调用子代理、search_knowledge、web_search、fetch_page 或 add_knowledge；工具返回后直接告知用户审核草稿已生成，不要输出过程性旁白。")
        if skill_instruction:
            parts.append(f"[本轮激活 Skill：{skill_name or '未命名'}]\n请遵循以下 Skill 指令处理用户问题：\n{skill_instruction}")
        knowledge_source = self.knowledge_orchestrator or self.knowledge
        if knowledge_enabled and knowledge_source is not None:
            try:
                if self.knowledge_orchestrator is not None:
                    context, found_citations = knowledge_source.context_for(user_message, session_id, knowledge_collection_id, knowledge_query_mode)
                else:
                    context, found_citations = knowledge_source.context_for(user_message, knowledge_collection_id, knowledge_query_mode)
                citations.extend(found_citations)
                if context:
                    parts.append(context)
            except Exception:
                pass
        if attachment_ids and self.attachment_service is not None:
            details = []
            for attachment_id in attachment_ids:
                try:
                    item = self.attachment_service.read(session_id, attachment_id)
                    details.append(f"- {item.original_name} (attachment_id: {attachment_id}; 提取状态: {item.extraction_status}; 来源: {', '.join(item.sources) or '无'})")
                except Exception:
                    details.append(f"- {attachment_id} (附件信息不可用)")
            parts.append("[当前消息附件]\n" + "\n".join(details))
        return "\n\n".join(part for part in parts if part)

    def _build_messages(self, session: Session, knowledge_collection_id: str | None = None, citations: list[dict] | None = None, knowledge_query_mode: str = "mix", knowledge_enabled: bool = False, response_mode: str = "fast") -> list[Message]:
        if self.compressor is not None and self.compressor.needs_compression(session.messages):
            session.messages = self.compressor.compress(session.messages)
            self.sessions.save(session)
        registry = self._registry_for(session.id, knowledge_collection_id)
        snapshot = self._ensure_runtime_snapshot(session, registry)
        messages = [Message(role="system", content=content) for content in snapshot.system_messages]
        for message in session.messages:
            if message.attachment_ids and self.attachment_service is not None:
                details = []
                image_urls: list[str] = []
                for attachment_id in message.attachment_ids:
                    try:
                        item = self.attachment_service.read(session.id, attachment_id)
                        details.append(f"- {item.original_name} (attachment_id: {attachment_id}; 提取状态: {item.extraction_status}; 来源: {', '.join(item.sources) or '无'})")
                        if self.vision_enabled and item.media_type.startswith("image/"):
                            handle = self.attachment_service.download_path(session.id, attachment_id)
                            try: image_urls.append(f"data:{item.media_type};base64,{base64.b64encode(handle.read_bytes()).decode('ascii')}")
                            finally: handle.close()
                    except Exception:
                        details.append(f"- {attachment_id} (附件信息不可用)")
                suffix = "\n图片已直接发送给视觉模型，请结合图片内容回答。" if image_urls else "\n如需读取附件内容，必须先调用 read_attachment，并使用对应的 attachment_id。"
                prompt_content = message.model_content
                if message.prompt_content is None:
                    prompt_content += "\n\n[当前消息附件]\n" + "\n".join(details) + suffix
                enriched = Message(role=message.role, content=message.content, prompt_content=prompt_content, runtime_epoch=message.runtime_epoch, tool_calls=message.tool_calls, tool_call_id=message.tool_call_id, name=message.name, attachment_ids=list(message.attachment_ids), image_urls=image_urls, id=message.id)
                messages.append(enriched)
            else:
                messages.append(message)
        return messages

    def run(self, session_id: str, user_message: str, attachment_ids: list[str] | None = None, knowledge_collection_id: str | None = None, knowledge_query_mode: str = "mix", knowledge_enabled: bool = False, is_cancelled: Callable[[], bool] | None = None, response_mode: str = "fast", toolsets: tuple[str, ...] | list[str] | None = None, skill_name: str | None = None, skill_instruction: str | None = None) -> Iterator[AgentEvent]:
        with self.sessions.session_lock(session_id):
            session = self.sessions.get(session_id)
            provider, owned_provider = self._provider_for_session(session)
            registry = self._registry_for(
                session_id,
                knowledge_collection_id,
                toolsets,
            )
            if self._is_fast_interview_collection_request(user_message) and "collect_interview_knowledge" in registry.names():
                registry = registry.subset(["collect_interview_knowledge"])
            elif not self._is_explicit_delegation_request(user_message):
                registry = registry.subset([name for name in registry.names() if not name.startswith("delegate_")])
            snapshot = self._ensure_runtime_snapshot(session, registry, provider)
            citations: list[dict] = []
            ids = list(attachment_ids or [])
            has_knowledge_pipeline = knowledge_enabled and (self.knowledge_orchestrator is not None or self.knowledge is not None)
            if has_knowledge_pipeline:
                yield AgentEvent("pipeline_stage", {"stage": "planning", "status": "completed", "detail": {"mode": knowledge_query_mode}})
                yield AgentEvent("pipeline_stage", {"stage": "retrieval", "status": "running", "detail": {}})
            prompt_content = self._turn_prompt(session_id, user_message, ids, response_mode, knowledge_collection_id, knowledge_query_mode, knowledge_enabled, citations, skill_name, skill_instruction)
            if has_knowledge_pipeline:
                routes = sorted({str(route) for citation in citations for route in citation.get("routes", []) if route})
                yield AgentEvent("pipeline_stage", {"stage": "retrieval", "status": "completed", "detail": {"citations": len(citations), "routes": routes}})
                reranked_citations = sum("reranker" in citation.get("routes", []) for citation in citations)
                if reranked_citations:
                    yield AgentEvent("pipeline_stage", {"stage": "rerank", "status": "completed", "detail": {"citations": reranked_citations}})
                yield AgentEvent("pipeline_stage", {"stage": "generation", "status": "running", "detail": {}})
            self.sessions.append(session_id, Message(role="user", content=user_message, prompt_content=prompt_content, runtime_epoch=snapshot.epoch, attachment_ids=ids))
            session = self.sessions.get(session_id)
            messages = self._build_messages(session, knowledge_collection_id)
            try:
                yield from self._run_loop(session_id, messages, registry, is_cancelled, citations, provider, owned_provider)
            finally:
                if owned_provider and not any(key[0] == session_id for key in self._pending_approvals):
                    getattr(provider, "close", lambda: None)()
            if self.profile_service is not None:
                self.profile_service.maybe_update(user_message)

    def regenerate(self, session_id: str, message_id: str, user_message: str, attachment_ids: list[str] | None = None, knowledge_collection_id: str | None = None, knowledge_query_mode: str = "mix", knowledge_enabled: bool = False, is_cancelled: Callable[[], bool] | None = None, toolsets: tuple[str, ...] | list[str] | None = None, skill_name: str | None = None, skill_instruction: str | None = None) -> Iterator[AgentEvent]:
        with self.sessions.session_lock(session_id):
            session = self.sessions.get(session_id)
            target = next((index for index, message in enumerate(session.messages) if message.id == message_id), None)
            if target is None:
                target = next((index for index in range(len(session.messages) - 1, -1, -1) if session.messages[index].role == "user" and session.messages[index].content == user_message), None)
            if target is None:
                target = next((index for index in range(len(session.messages) - 1, -1, -1) if session.messages[index].role == "user"), None)
            if target is None:
                raise ValidationError("要重新生成的消息不存在，请刷新页面后重试")
            user_index = next((index for index in range(target, -1, -1) if session.messages[index].role == "user"), None)
            if user_index is None:
                raise ValidationError("未找到对应的用户消息，请刷新页面后重试")
            original = session.messages[user_index]
            session.messages = session.messages[:user_index]
            self.sessions.save(session)
            yield from self.run(session_id, user_message or original.content, attachment_ids if attachment_ids is not None else original.attachment_ids, knowledge_collection_id, knowledge_query_mode, knowledge_enabled, is_cancelled, toolsets=toolsets, skill_name=skill_name, skill_instruction=skill_instruction)

    def resolve_tool_approval(self, session_id: str, call_id: str, approved: bool) -> Iterator[AgentEvent]:
        with self.sessions.session_lock(session_id):
            with self._approval_lock:
                pending = self._pending_approvals.pop((session_id, call_id), None)
            if pending is None:
                raise ToolApprovalNotFoundError("待确认的工具调用不存在或已处理")
            call, registry, is_cancelled, citations, provider, owned_provider = pending
            if is_cancelled():
                return
            if call.name == "request_subagent_collaboration":
                registry.replace_prefix("request_subagent_collaboration", [])
                if approved:
                    for delegation_tool in self.loop.tools.tools_with_prefix("delegate_"):
                        registry.register(delegation_tool)
            if approved:
                for event in self.loop.execute_tool_call(call, registry, is_cancelled):
                    if event.type == "tool_finished": self._persist_tool_result(session_id, event)
                    yield event
            else:
                event = self._tool_finished_event(call, ToolExecutionResult(False, error_code="tool_approval_rejected", error_message="用户拒绝执行此工具调用"))
                self._persist_tool_result(session_id, event)
                yield event
            if is_cancelled(): return
            session = self.sessions.get(session_id)
            messages = self._build_messages(session)
            try:
                yield from self._run_loop(session_id, messages, registry, is_cancelled, citations, provider, owned_provider)
            finally:
                if owned_provider:
                    getattr(provider, "close", lambda: None)()

    def cancel_tool_approval(self, session_id: str, call_id: str) -> bool:
        """Discard a pending approval without invoking its tool."""
        with self._approval_lock:
            pending = self._pending_approvals.pop((session_id, call_id), None)
        if pending is not None and pending[5]:
            getattr(pending[4], "close", lambda: None)()
        return pending is not None

    def _registry_for(self, session_id: str, knowledge_collection_id: str | None = None, toolsets: tuple[str, ...] | list[str] | None = None) -> ToolRegistry:
        registry = self.loop.tools.copy()
        if self.delegation_service is not None:
            from iris_agent.tools.builtin.subagent_tool import build_delegate_task_tool
            registry.replace_prefix("delegate_task", [build_delegate_task_tool(self.delegation_service, session_id=session_id)])
        if self.knowledge is not None:
            from iris_agent.tools.builtin.knowledge_tools import build_search_knowledge_tool
            registry.replace_prefix("search_knowledge", [build_search_knowledge_tool(self.knowledge, knowledge_collection_id)])
        if self.attachment_service is not None:
            from iris_agent.tools.builtin.attachments import build_read_attachment_tool
            registry.register(build_read_attachment_tool(self.attachment_service, session_id))
        if toolsets is not None and self.capability_resolver is not None:
            return self.capability_resolver.resolve(toolsets, registry)
        return registry

    @staticmethod
    def _is_fast_interview_collection_request(message: str) -> bool:
        normalized = message.lower()
        has_direct_url = bool(re.search(r"https?://", normalized))
        return (
            bool(re.search(r"面经|面试题|interview", normalized))
            and bool(re.search(r"搜索|搜集|收集|查找|抓取", normalized))
            and (bool(re.search(r"知识库|入库|保存", normalized)) or has_direct_url)
        )

    @staticmethod
    def _is_explicit_delegation_request(message: str) -> bool:
        return bool(re.search(r"子代理|分工|并行协作|多代理|多个代理", message, re.IGNORECASE))


    def _run_loop(self, session_id: str, messages: list[Message], registry: ToolRegistry, is_cancelled: Callable[[], bool] | None = None, citations: list[dict] | None = None, provider: ModelProvider | None = None, owned_provider: bool = False) -> Iterator[AgentEvent]:
        cancelled = is_cancelled or (lambda: False)
        for event in self.loop._run_with_provider(provider or self.loop.get_provider(), messages, registry, cancelled):
            if event.type == "tool_started":
                call = ToolCall(str(event.data["call_id"]), str(event.data["name"]), dict(event.data.get("arguments", {})))
                self.sessions.append(session_id, Message(role="assistant", tool_calls=[call]))
            elif event.type == "tool_approval_requested":
                call = ToolCall(str(event.data["call_id"]), str(event.data["name"]), dict(event.data.get("arguments", {})))
                with self._approval_lock:
                    self._pending_approvals[(session_id, call.id)] = (call, registry, cancelled, list(citations or []), provider or self.loop.get_provider(), owned_provider)
            elif event.type == "tool_finished":
                self._persist_tool_result(session_id, event)
            elif event.type == "message_completed":
                citation_items = list(citations or [])
                message = Message(role="assistant", content=str(event.data.get("content", "")), citations=citation_items)
                self.sessions.append(session_id, message)
                yield AgentEvent("message_completed", {
                    "message_id": message.id,
                    "citations": citation_items,
                    "follow_up_suggestions": self._follow_up_suggestions(citation_items),
                    "metrics": event.data.get("metrics"),
                })
                continue
            yield event

    @staticmethod
    def _follow_up_suggestions(citations: list[dict]) -> list[str]:
        titles = list(dict.fromkeys(
            title for citation in citations
            if isinstance(citation, dict) and isinstance(title := citation.get("title"), str) and title.strip()
        ))
        suggestions = [f"请展开说明《{title}》中的关键细节。" for title in titles[:3]]
        fallback = ("基于这些资料，下一步可以怎么做？", "这份资料的结论有哪些适用边界？")
        for item in fallback:
            if len(suggestions) >= 3:
                break
            suggestions.append(item)
        return suggestions

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
