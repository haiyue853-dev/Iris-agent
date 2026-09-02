"""Ollama-backed entity and relation extraction for local knowledge graphs."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from iris_agent.knowledge.mindmap import MindMapNode, normalise_mindmap_payload, select_mindmap_chunks


_ENTITY_ALIASES = {
    "javascript": "JavaScript", "js": "JavaScript", "typescript": "TypeScript", "ts": "TypeScript",
    "reactjs": "React", "react.js": "React", "vuejs": "Vue", "vue.js": "Vue",
    "nodejs": "Node.js", "node.js": "Node.js", "mysql数据库": "MySQL", "mysql": "MySQL",
    "redis缓存": "Redis", "redis": "Redis", "kubernetes": "Kubernetes", "k8s": "Kubernetes",
}
_RELATION_ALIASES = {"使用": "使用", "采用": "使用", "基于": "基于", "依赖": "依赖", "包含": "包含", "组成": "包含", "实现": "实现", "用于": "用于", "导致": "导致", "优化": "优化", "关联": "关联", "涉及": "涉及"}


def canonical_graph_label(value: object) -> str:
    """Make equivalent spelling variants resolve to one graph node."""
    label = re.sub(r"\s+", " ", str(value or "").strip()).strip("，。；：、（）()[]【】\"'")[:48]
    if not label:
        return ""
    return _ENTITY_ALIASES.get(label.casefold(), label)


def canonical_graph_relation(value: object) -> str:
    relation = re.sub(r"\s+", " ", str(value or "关联").strip())[:40]
    return _RELATION_ALIASES.get(relation, "关联" if len(relation) < 2 else relation)


class OllamaGraphExtractor:
    """Uses a local instruct model; callers may safely fall back on failure."""

    def __init__(self, *, model: str, base_url: str, timeout: float = 120) -> None:
        self.model = model.strip()
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=timeout)

    def extract(self, title: str, content: str) -> tuple[list[tuple[str, str]], list[tuple[str, str, str]]]:
        prompt = f"""从下面的中文资料中提取知识图谱。只返回 JSON，不要解释：
{{"entities":[{{"name":"实体","type":"概念"}}],"relations":[{{"source":"实体","target":"实体","relation":"关系"}}]}}
规则：提取 4 到 12 个对理解资料真正重要的实体；实体名用最常见的标准写法（例如 React，不要 React.js/reactjs；Node.js，不要 nodejs）；不要把句子、章节标题、作者、目录、页码、泛泛的“本文/资料”当实体；关系只能用“使用、基于、依赖、包含、实现、用于、导致、优化、关联、涉及”之一；实体名不超过 48 字。
资料标题：{title[:200]}
资料正文：{content[:12000]}"""
        response = self.client.post(
            f"{self.base_url}/api/generate",
            json={"model": self.model, "prompt": prompt, "format": "json", "stream": False, "options": {"temperature": 0}},
        )
        response.raise_for_status()
        payload = response.json()
        raw = payload.get("response") or payload.get("thinking") or ""
        if not isinstance(raw, str):
            raise ValueError("Ollama graph response is invalid")
        parsed: dict[str, Any] = json.loads(raw)
        return self._normalise(parsed, title)

    def outline(self, title: str, content: str) -> tuple[list[tuple[str, str]], list[tuple[str, str, str]]]:
        """Build a document-level concept spine before adding chunk evidence."""
        prompt = f"""根据整份资料归纳知识图谱的一级结构。只返回 JSON，不要解释：
{{"concepts":["核心概念"],"relations":[{{"source":"核心概念","target":"核心概念","relation":"依赖"}}]}}
规则：仅保留 3 到 6 个能够概括全文的一级概念；不要使用段落句子、目录、作者或“本文/资料”；概念用标准技术名；关系只能用“使用、基于、依赖、包含、实现、用于、导致、优化、关联、涉及”。
资料标题：{title[:200]}
资料正文：{content[:40000]}"""
        response = self.client.post(f"{self.base_url}/api/generate", json={"model": self.model, "prompt": prompt, "format": "json", "stream": False, "options": {"temperature": 0}})
        response.raise_for_status()
        payload = response.json(); raw = payload.get("response") or payload.get("thinking") or ""
        if not isinstance(raw, str):
            raise ValueError("Ollama outline response is invalid")
        parsed: dict[str, Any] = json.loads(raw)
        concepts = []
        for value in parsed.get("concepts", []) if isinstance(parsed.get("concepts"), list) else []:
            label = canonical_graph_label(value)
            if len(label) >= 2 and label not in {item[0] for item in concepts}:
                concepts.append((label, "core"))
            if len(concepts) == 6:
                break
        known = {name for name, _ in concepts}
        relations = []
        for item in parsed.get("relations", []) if isinstance(parsed.get("relations"), list) else []:
            if not isinstance(item, dict):
                continue
            source, target = canonical_graph_label(item.get("source")), canonical_graph_label(item.get("target"))
            if source in known and target in known and source != target:
                relation = canonical_graph_relation(item.get("relation"))
                if (source, target, relation) not in relations:
                    relations.append((source, target, relation))
        return concepts, relations

    def mind_map(self, title: str, chunks: list[Any]) -> list[MindMapNode]:
        """Summarise one complete document into a bounded three-level tree."""
        excerpts = [{"ordinal": item.ordinal, "content": item.content[:5000]} for item in select_mindmap_chunks(chunks, limit=24)]
        prompt = f"""根据整份资料生成文档思维导图。只返回 JSON，不要解释：
{{"summary":"全文总结","branches":[{{"title":"一级主题","summary":"主题总结","evidence_ordinals":[0],"children":[{{"title":"关键观点","summary":"观点说明","evidence_ordinals":[0]}}]}}]}}
严格规则：必须从全文层面归纳；输出 3 到 8 个一级主题，每个主题 2 到 6 个关键观点；最多三层；节点标题必须是 2 到 20 字的概念短语，禁止复制完整句子；全文总节点不得超过 40；summary 为 30 到 120 字；evidence_ordinals 只能引用给定切片编号；不要输出作者、目录、页码或“本文/资料”。
资料标题：{title[:200]}
资料切片：{json.dumps(excerpts, ensure_ascii=False)[:40000]}"""
        response = self.client.post(f"{self.base_url}/api/generate", json={"model": self.model, "prompt": prompt, "format": "json", "stream": False, "options": {"temperature": 0}})
        response.raise_for_status()
        payload = response.json()
        raw = payload.get("response") or payload.get("thinking") or ""
        if not isinstance(raw, str):
            raise ValueError("Ollama mind map response is invalid")
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("Ollama mind map response is invalid")
        nodes = normalise_mindmap_payload(title, parsed, chunks)
        if len(nodes) < 2:
            raise ValueError("Ollama mind map has no branches")
        return nodes




    def aliases(self, labels: list[str]) -> dict[str, str]:
        """Ask the local model to merge only unambiguous synonymous entity names."""
        values = [canonical_graph_label(label) for label in labels if canonical_graph_label(label)]
        if len(values) < 2:
            return {}
        prompt = f"""判断下面知识图谱实体中是否有明确的同义词、英文大小写/缩写/版本写法差异。只返回 JSON：{{"aliases":[{{"from":"旧名称","to":"标准名称"}}]}}。
严格规则：仅在含义完全相同时合并；不要把上下位概念、相关概念或带不同限定词的概念合并；若不确定则不要输出。标准名称优先使用通用技术名。
实体：{json.dumps(values[:120], ensure_ascii=False)}"""
        response = self.client.post(f"{self.base_url}/api/generate", json={"model": self.model, "prompt": prompt, "format": "json", "stream": False, "options": {"temperature": 0}})
        response.raise_for_status(); payload = response.json(); raw = payload.get("response") or payload.get("thinking") or ""
        parsed = json.loads(raw); known = set(values); aliases: dict[str, str] = {}
        for item in parsed.get("aliases", []) if isinstance(parsed.get("aliases"), list) else []:
            if not isinstance(item, dict):
                continue
            source, target = canonical_graph_label(item.get("from")), canonical_graph_label(item.get("to"))
            if source in known and target in known and source != target:
                aliases[source] = target
        return aliases

    def summarize_graph_item(self, label: str, facts: list[str], *, kind: str) -> str:
        """Return a concise grounded Chinese description for one node or one relation."""
        evidence = "\n".join(f"- {item[:420]}" for item in facts[:6])
        prompt = f"""根据下列知识图谱事实与原文证据，为{kind}“{label[:100]}”写一条 35 到 90 字的中文摘要。
只陈述证据明确支持的内容；不要补充外部知识、不要使用“该资料指出”等套话；无足够证据时输出“暂无足够来源证据”。只输出摘要正文。
证据：\n{evidence}"""
        response = self.client.post(f"{self.base_url}/api/generate", json={"model": self.model, "prompt": prompt, "stream": False, "options": {"temperature": 0}})
        response.raise_for_status()
        raw = response.json().get("response") or ""
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("Ollama graph summary response is invalid")
        return re.sub(r"\s+", " ", raw).strip()[:240]

    def evaluation_cases(self, documents: list[dict[str, str]]) -> list[dict[str, str]]:
        """Generate grounded retrieval evaluation cases from local document excerpts."""
        prompt = f"""根据下列本地知识资料生成 6 到 12 条中文 RAG 回归评测用例。只返回 JSON：
{{"cases":[{{"question":"具体问题","expected_title":"必须匹配的资料标题","expected_answer":"基于资料的一句标准答案"}}]}}
规则：问题须能由给定资料直接回答，覆盖事实、归纳和关系理解；不要使用资料外知识；expected_title 必须完全来自资料标题；每个问题不要超过 60 字。
资料：{json.dumps(documents[:8], ensure_ascii=False)}"""
        response = self.client.post(f"{self.base_url}/api/generate", json={"model": self.model, "prompt": prompt, "format": "json", "stream": False, "options": {"temperature": 0}})
        response.raise_for_status(); raw = response.json().get("response") or response.json().get("thinking") or ""
        parsed = json.loads(raw); titles = {item["title"] for item in documents}; cases: list[dict[str, str]] = []
        for item in parsed.get("cases", []) if isinstance(parsed.get("cases"), list) else []:
            if not isinstance(item, dict): continue
            question = re.sub(r"\s+", " ", str(item.get("question") or "")).strip()[:120]
            title = str(item.get("expected_title") or "").strip()[:200]
            answer = re.sub(r"\s+", " ", str(item.get("expected_answer") or "")).strip()[:500]
            if question and title in titles and (question, title) not in {(case["question"], case["expected_title"]) for case in cases}:
                cases.append({"question": question, "expected_title": title, "expected_answer": answer})
            if len(cases) >= 12: break
        return cases

    def evaluate_retrieval_answer(self, question: str, expected_answer: str, sources: list[str]) -> dict[str, object]:
        """Produce and judge a grounded answer in one local-model pass for regression evaluation."""
        evidence = "\n\n".join(f"[{index + 1}] {item[:900]}" for index, item in enumerate(sources[:3]))
        prompt = f"""你是本地 RAG 评测器。只依据给定检索证据回答问题，并评估回答与参考答案的一致性。只返回 JSON：
{{"answer":"简洁回答，带[1]引用","answer_score":0到1小数,"grounded":true或false,"reason":"不超过50字"}}
问题：{question[:160]}
参考答案：{expected_answer[:500]}
检索证据：{evidence}"""
        response = self.client.post(f"{self.base_url}/api/generate", json={"model": self.model, "prompt": prompt, "format": "json", "stream": False, "options": {"temperature": 0}})
        response.raise_for_status(); raw = response.json().get("response") or response.json().get("thinking") or ""
        parsed = json.loads(raw)
        score = max(0.0, min(float(parsed.get("answer_score", 0)), 1.0))
        return {"answer": str(parsed.get("answer") or "").strip()[:800], "answer_score": round(score, 3), "grounded": bool(parsed.get("grounded")), "reason": str(parsed.get("reason") or "").strip()[:160]}

    def close(self) -> None:
        self.client.close()

    @staticmethod
    def _normalise(payload: dict[str, Any], title: str) -> tuple[list[tuple[str, str]], list[tuple[str, str, str]]]:
        banned = {"本文", "资料", "文档", "目录", "摘要", "作者", "姓名", "页码", "内容", "项目", "介绍"}
        entities: list[tuple[str, str]] = [(title.strip()[:120], "topic")]
        known = {entities[0][0]} if entities[0][0] else set()
        for item in payload.get("entities", []) if isinstance(payload.get("entities"), list) else []:
            if not isinstance(item, dict):
                continue
            name = canonical_graph_label(item.get("name", ""))
            kind = re.sub(r"\s+", " ", str(item.get("type", "概念")).strip())[:32] or "概念"
            if len(name) < 2 or name in banned or name in known:
                continue
            known.add(name); entities.append((name, kind))
            if len(entities) >= 13:
                break
        relations: list[tuple[str, str, str]] = []
        for item in payload.get("relations", []) if isinstance(payload.get("relations"), list) else []:
            if not isinstance(item, dict):
                continue
            source, target = canonical_graph_label(item.get("source", "")), canonical_graph_label(item.get("target", ""))
            relation = canonical_graph_relation(item.get("relation", "关联"))
            if source in known and target in known and source != target and (source, target, relation) not in relations:
                relations.append((source, target, relation))
        topic = entities[0][0] if entities else ""
        linked = {part for edge in relations for part in edge[:2]}
        for name, _ in entities[1:]:
            if name not in linked:
                relations.append((topic, name, "涉及"))
        return entities, relations
