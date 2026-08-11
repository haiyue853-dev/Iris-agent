from pydantic import BaseModel, Field


class GenerateDocumentDraftRequest(BaseModel):
    template: str = Field(min_length=1, max_length=64)
    document_ids: list[str] = Field(default_factory=list)
    instructions: str = Field(default="", max_length=2_000)


class SaveDocumentDraftRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    markdown: str = Field(min_length=1)
    expected_revision: int = Field(ge=1)
