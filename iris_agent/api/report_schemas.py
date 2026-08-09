from pydantic import BaseModel, Field, model_validator

from iris_agent.reports.models import ReportSections


class ReportSectionsSchema(BaseModel):
    completed: list[str] = Field(default_factory=list)
    in_progress: list[str] = Field(default_factory=list)
    problems: list[str] = Field(default_factory=list)
    next_day: list[str] = Field(default_factory=list)
    assistance: list[str] = Field(default_factory=list)

    def to_model(self) -> ReportSections:
        return ReportSections.from_mapping(self.model_dump())


class _RevisionRequest(BaseModel):
    """Accept the legacy field temporarily, but always resolve a write revision."""

    expected_revision: int | None = Field(default=None, ge=0)
    expected_version: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _require_one_revision(self):
        if self.expected_revision is None and self.expected_version is None:
            raise ValueError("expected revision is required")
        if (
            self.expected_revision is not None
            and self.expected_version is not None
            and self.expected_revision != self.expected_version
        ):
            raise ValueError("expected revision values disagree")
        return self

    @property
    def write_revision(self) -> int:
        return self.expected_revision if self.expected_revision is not None else self.expected_version  # type: ignore[return-value]


class GenerateReportRequest(BaseModel):
    date: str
    notes: str = ""
    include_chat: bool = False
    session_id: str | None = None
    expected_revision: int | None = Field(default=None, ge=0)
    expected_version: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _matching_optional_revisions(self):
        if (
            self.expected_revision is not None
            and self.expected_version is not None
            and self.expected_revision != self.expected_version
        ):
            raise ValueError("expected revision values disagree")
        return self

    @property
    def write_revision(self) -> int | None:
        return self.expected_revision if self.expected_revision is not None else self.expected_version


class SaveReportRequest(_RevisionRequest):
    sections: ReportSectionsSchema


class ReviseReportRequest(_RevisionRequest):
    instruction: str


class RestoreReportRequest(_RevisionRequest):
    pass


class ReportChatRequest(_RevisionRequest):
    message: str = Field(min_length=1, max_length=2_000)
    attachment_ids: list[str] = Field(default_factory=list)


class ApplySuggestionRequest(_RevisionRequest):
    pass
