from __future__ import annotations

from iris_agent.knowledge.semantic_splitter import LocalSemanticSplitter


class TopicEmbedder:
    model = "bge-m3"
    base_url = "http://localhost:11434"

    def __init__(self):
        self.calls: list[list[str]] = []

    def embed(self, texts):
        batch = list(texts)
        self.calls.append(batch)
        vectors = []
        for text in batch:
            if "安装" in text or "配置" in text:
                vectors.append([1.0, 0.0])
            else:
                vectors.append([0.0, 1.0])
        return vectors


def test_local_splitter_breaks_unstructured_long_text_at_a_topic_change():
    embedder = TopicEmbedder()
    splitter = LocalSemanticSplitter(embedder, similarity_threshold=0.5, minimum_input_chars=20)
    text = "安装前需要准备环境。配置文件需要填写端口。\n\n运行服务后检查日志。排错时先检查网络。"

    chunks = splitter.split("使用手册", text, target_chars=28)

    assert len(chunks) == 2
    assert "配置文件" in chunks[0].content
    assert "运行服务" in chunks[1].content
    assert "".join(chunk.content for chunk in chunks) == text
    assert len(embedder.calls) == 1


def test_local_splitter_defers_structured_documents_to_heading_chunking():
    embedder = TopicEmbedder()
    splitter = LocalSemanticSplitter(embedder, minimum_input_chars=1)

    chunks = splitter.split("面试题", "# 第一题\n答案一\n\n# 第二题\n答案二", target_chars=20)

    assert chunks == []
    assert embedder.calls == []


def test_local_splitter_skips_short_text_without_calling_the_model():
    embedder = TopicEmbedder()
    splitter = LocalSemanticSplitter(embedder, minimum_input_chars=100)

    assert splitter.split("短文", "只有一个短段落。", target_chars=20) == []
    assert embedder.calls == []
