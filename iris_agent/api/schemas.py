from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(default="")
    attachment_ids: list[str] = Field(default_factory=list, max_length=10)
    knowledge_collection_id: str | None = Field(default=None, max_length=50)
    knowledge_query_mode: Literal["precise", "global", "mix"] = "mix"
    use_knowledge: bool = False
    response_mode: Literal["fast", "thinking"] = "fast"
    toolsets: list[Literal["safe", "research", "coding", "knowledge", "skills", "delegation"]] | None = None
    skill_id: str | None = Field(default=None, max_length=200)
    regenerate_from_message_id: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def require_message_or_attachment(self):
        if not self.message.strip() and not self.attachment_ids:
            raise ValueError("message or attachment_ids is required")
        return self


class CreateSessionRequest(BaseModel):
    name: str = Field(default="新对话", max_length=100)
    model_profile_id: str | None = Field(default=None, max_length=200)


class PromptOptimizationRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def require_non_blank_prompt(self):
        if not self.prompt.strip():
            raise ValueError("prompt is required")
        return self


class SessionModelProfileRequest(BaseModel):
    model_profile_id: str | None = Field(default=None, max_length=200)


class QueueTaskRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1)


class ToolApprovalRequest(BaseModel):
    approved: bool


class MemoryCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    category: Literal["preference", "fact", "project", "other"] = "fact"


class ProfileUpdateRequest(BaseModel):
    name: str = Field(default="", max_length=200)
    preferences: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    style: str = Field(default="", max_length=500)
    facts: list[str] = Field(default_factory=list)


class KnowledgeCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=50000)
    category: str = Field(default="面经", max_length=50)
    source_url: str | None = Field(default=None, max_length=2000)
    collection_id: str = Field(default="collection-general", max_length=50)


class KnowledgeUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=50000)


class KnowledgeChunkUpdateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=50000)
    location: str | None = Field(default=None, max_length=500)


class KnowledgeImportRequest(BaseModel):
    backup: dict
    collection_id: str = Field(min_length=1, max_length=50)


class KnowledgeEvaluationRequest(BaseModel):
    questions: list[str] = Field(default_factory=list, max_length=200)
    cases: list[dict] = Field(default_factory=list, max_length=200)
    k_values: list[int] = Field(default_factory=lambda: [1, 3, 5, 10], min_length=1, max_length=10)
    collection_id: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def require_questions_or_cases(self):
        if not self.questions and not self.cases:
            raise ValueError("questions or cases is required")
        if any(isinstance(value, bool) or value < 1 or value > 50 for value in self.k_values):
            raise ValueError("k_values must contain integers from 1 to 50")
        self.k_values = sorted(set(self.k_values))
        return self


class KnowledgeGraphSummaryRequest(BaseModel):
    kind: Literal["entity", "relation"]
    node_id: str | None = Field(default=None, max_length=100)
    source_id: str | None = Field(default=None, max_length=100)
    target_id: str | None = Field(default=None, max_length=100)
    relation: str | None = Field(default=None, max_length=80)
    document_id: str | None = Field(default=None, max_length=100)
    collection_id: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def require_graph_target(self):
        if self.kind == "entity" and not self.node_id:
            raise ValueError("node_id is required")
        if self.kind == "relation" and not (self.source_id and self.target_id and self.relation):
            raise ValueError("source_id, target_id and relation are required")
        return self


class KnowledgeGraphRelationEditRequest(BaseModel):
    source_id: str = Field(min_length=1, max_length=100)
    target_id: str = Field(min_length=1, max_length=100)
    relation: str = Field(min_length=1, max_length=80)
    document_id: str | None = Field(default=None, max_length=100)
    new_relation: str | None = Field(default=None, max_length=80)


class KnowledgeGraphEntityEditRequest(BaseModel):
    node_id: str = Field(min_length=1, max_length=100)
    collection_id: str = Field(min_length=1, max_length=50)
    label: str | None = Field(default=None, max_length=120)


class KnowledgeEvaluationGenerateRequest(BaseModel):
    collection_id: str | None = Field(default=None, max_length=50)


class KnowledgeEvaluationSeedRequest(BaseModel):
    cases: list[dict] = Field(min_length=1, max_length=200)
    collection_id: str | None = Field(default=None, max_length=50)


class KnowledgeEvaluationGateUpdateRequest(BaseModel):
    recall_at_1: float = Field(ge=0, le=1)
    recall_at_3: float = Field(ge=0, le=1)
    mrr: float = Field(ge=0, le=1)


class KnowledgeBadCaseRequest(BaseModel):
    question: str = Field(min_length=1, max_length=10000)
    collection_id: str | None = Field(default=None, max_length=50)
    expected_title: str | None = Field(default=None, max_length=200)
    relevant_chunk_ids: list[str] = Field(default_factory=list, max_length=100)
    relevant_document_ids: list[str] = Field(default_factory=list, max_length=100)
    expected_answer: str = Field(default="", max_length=50000)
    actual_answer: str = Field(default="", max_length=50000)
    reason: str = Field(default="", max_length=1000)


class KnowledgeUploadRequest(BaseModel):
    title: str = Field(default="", max_length=200)
    original_name: str = Field(min_length=1, max_length=255)
    media_type: str | None = Field(default=None, max_length=200)
    content_base64: str = Field(min_length=1)
    collection_id: str = Field(default="collection-general", max_length=50)


class KnowledgeRuntimeUpdateRequest(BaseModel):
    embedding_enabled: bool | None = None
    embedding_model: str | None = Field(default=None, min_length=1, max_length=200)
    embedding_base_url: str | None = Field(default=None, min_length=1, max_length=500)
    semantic_split_enabled: bool | None = None
    semantic_split_model: str | None = Field(default=None, min_length=1, max_length=200)
    semantic_split_base_url: str | None = Field(default=None, min_length=1, max_length=500)
    graph_enabled: bool | None = None
    graph_model: str | None = Field(default=None, min_length=1, max_length=200)
    graph_base_url: str | None = Field(default=None, min_length=1, max_length=500)
    image_enabled: bool | None = None
    image_model: str | None = Field(default=None, min_length=1, max_length=200)
    image_base_url: str | None = Field(default=None, min_length=1, max_length=500)
    reranker_enabled: bool | None = None
    reranker_provider: Literal["ollama", "api", "fastembed", "none"] | None = None
    reranker_model: str | None = Field(default=None, min_length=1, max_length=200)
    reranker_base_url: str | None = Field(default=None, min_length=1, max_length=500)
    mmr_relevance_weight: float | None = Field(default=None, ge=0, le=1)


class KnowledgeRuntimeTestRequest(BaseModel):
    component: Literal["embedding", "graph", "image", "reranker"] | None = None


class KnowledgeCollectionCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=300)


class KnowledgeCollectionRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class KnowledgeCollectionRetrievalConfigUpdateRequest(BaseModel):
    top_k: int | None = Field(default=None, ge=1, le=20)
    candidate_multiplier: int | None = Field(default=None, ge=1, le=10)
    minimum_relevance_score: float | None = Field(default=None, ge=0, le=1)
    mmr_relevance_weight: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def require_retrieval_config_value(self):
        if all(value is None for value in self.model_dump().values()):
            raise ValueError("至少提供一项检索策略")
        return self


class KnowledgeDocumentMoveRequest(BaseModel):
    collection_id: str = Field(min_length=1, max_length=50)


class CuratorApplyRequest(BaseModel):
    suggestion_ids: list[str] | None = None
    all: bool = False
