from pydantic import BaseModel, Field

from iris_agent.reports.models import ReportSections


class ReportSectionsSchema(BaseModel):
    completed: list[str] = Field(default_factory=list)
    in_progress: list[str] = Field(default_factory=list)
    problems: list[str] = Field(default_factory=list)
    next_day: list[str] = Field(default_factory=list)
    assistance: list[str] = Field(default_factory=list)

    def to_model(self) -> ReportSections:
        return ReportSections.from_mapping(self.model_dump())


class GenerateReportRequest(BaseModel):
    date: str
    notes: str = ""
    include_chat: bool = False
    session_id: str | None = None
    expected_version: int | None = Field(default=None, ge=0)


class SaveReportRequest(BaseModel):
    sections: ReportSectionsSchema
    expected_version: int = Field(ge=0)


class ReviseReportRequest(BaseModel):
    instruction: str
    expected_version: int = Field(ge=0)


class RestoreReportRequest(BaseModel):
    expected_version: int = Field(ge=0)
