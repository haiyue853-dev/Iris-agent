# Iris Agent 日报助手实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 `subagent-driven-development`（推荐）或 `executing-plans` 逐任务实现此计划。步骤使用复选框（`- [ ]`）跟踪进度。

**目标：** 为 Iris Agent 增加独立的三栏日报工作台，支持手动记录、导入当前会话、汇报版生成、结构化编辑、AI 修改、本地版本历史、复制和 Markdown 下载。

**架构：** 新建独立的 `reports` 领域包，通过 `DailyReportService` 直接调用现有 `ModelProvider` 和 `SessionRepository`，不经过 Agent 工具循环。报告以每日期一个 JSON 文件原子保存，前端通过专用 API 和 Hook 管理生成、自动保存、版本冲突和历史，并在桌面端渲染三栏布局。

**技术栈：** Python 3.11+、dataclasses、FastAPI、pytest、React 19、TypeScript、Vite、Vitest、Testing Library。

---

## 文件结构

### 后端新增

- `iris_agent/reports/__init__.py`：导出日报公共类型和服务。
- `iris_agent/reports/models.py`：章节、来源消息、版本、日报和摘要模型。
- `iris_agent/reports/errors.py`：日报稳定领域错误。
- `iris_agent/reports/repository.py`：仓库协议与原子 JSON 实现。
- `iris_agent/reports/prompts.py`：汇报版生成和修改提示词。
- `iris_agent/reports/service.py`：生成、保存、修改、恢复和 Markdown 渲染。
- `iris_agent/api/report_schemas.py`：Pydantic 请求和响应模型。
- `tests/reports/test_models.py`：模型不可变性和校验。
- `tests/reports/test_repository.py`：原子存储、并发和版本上限。
- `tests/reports/test_service.py`：模型调用、会话导入、版本操作和 Markdown。
- `tests/api/test_reports.py`：日报 HTTP 合约和错误码。

### 后端修改

- `iris_agent/core/errors.py`：允许日报错误沿用统一安全响应。
- `iris_agent/config/settings.py`：增加 `ReportSettings`。
- `agent.yaml`：增加日报默认配置。
- `iris_agent/bootstrap.py`：组装日报仓库和服务。
- `iris_agent/api/app.py`：可选注册日报路由。
- `server.py`：把日报服务传给 FastAPI。
- `iris_agent/cli.py`：适配新的应用组装返回值。
- `tests/config/test_settings.py`：日报配置验证。
- `tests/api/test_app.py`：保持现有聊天 API 回归。

### 前端新增

- `web-react/src/api/reports.ts`：日报 HTTP 客户端。
- `web-react/src/hooks/useDailyReports.ts`：日报状态、自动保存和并发控制。
- `web-react/src/components/reports/DailyReportPage.tsx`：三栏页面容器。
- `web-react/src/components/reports/ReportHistory.tsx`：日期历史和版本入口。
- `web-react/src/components/reports/ReportSourceEditor.tsx`：来源记录和会话开关。
- `web-react/src/components/reports/ReportPreview.tsx`：五章节编辑、复制和下载。
- `web-react/src/components/reports/ReportRevisionBox.tsx`：AI 修改输入。
- `web-react/src/hooks/useDailyReports.test.tsx`：Hook 的生成、保存和错误测试。
- `web-react/src/components/reports/DailyReportPage.test.tsx`：页面关键交互测试。
- `web-react/src/test/setup.ts`：Vitest DOM 测试环境。

### 前端修改

- `web-react/package.json`：增加 `test` 脚本和测试依赖。
- `web-react/vite.config.ts`：增加 Vitest 配置。
- `web-react/src/types.ts`：日报类型。
- `web-react/src/App.tsx`：聊天/日报视图切换。
- `web-react/src/components/Sidebar.tsx`：增加日报入口。
- `web-react/src/App.css`：三栏和窄屏布局。

### 文档修改

- `README.md`：日报使用、数据位置和限制。
- `.env.example`：无需增加密钥，只补充日报说明时才修改。

---

## 任务 1：日报领域模型与错误

**文件：**
- 创建：`iris_agent/reports/__init__.py`
- 创建：`iris_agent/reports/models.py`
- 创建：`iris_agent/reports/errors.py`
- 测试：`tests/reports/test_models.py`

- [ ] **步骤 1：编写模型失败测试**

```python
def test_report_sections_are_immutable():
    source = ["完成日报设计"]
    sections = ReportSections(completed=source)
    source.append("外部修改")
    assert sections.completed == ("完成日报设计",)


def test_daily_report_current_version_must_exist():
    with pytest.raises(ReportValidationError):
        DailyReport.create("2026-08-05", "记录", None, (), versions=[], current_version=1)
```

- [ ] **步骤 2：运行测试确认模块缺失**

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/reports/test_models.py -q`

预期：FAIL，错误为 `ModuleNotFoundError: iris_agent.reports`。

- [ ] **步骤 3：实现领域类型和稳定错误**

实现以下公开接口：

```python
@dataclass(frozen=True, slots=True)
class ReportSections:
    completed: tuple[str, ...] = ()
    in_progress: tuple[str, ...] = ()
    problems: tuple[str, ...] = ()
    next_day: tuple[str, ...] = ()
    assistance: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "ReportSections":
        expected = {"completed", "in_progress", "problems", "next_day", "assistance"}
        if set(raw) != expected:
            raise ReportValidationError("日报章节字段无效")
        normalized: dict[str, tuple[str, ...]] = {}
        for key in expected:
            value = raw[key]
            if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) for item in value):
                raise ReportValidationError(f"日报章节 {key} 必须是字符串数组")
            normalized[key] = tuple(item.strip() for item in value if item.strip())
        return cls(**normalized)


@dataclass(frozen=True, slots=True)
class ReportSourceMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class ReportVersion:
    number: int
    sections: ReportSections
    kind: Literal["generated", "manual", "ai_revision", "restored"]
    instruction: str | None
    created_at: float


@dataclass(slots=True)
class DailyReport:
    date: str
    source_notes: str
    source_session_id: str | None
    source_chat_snapshot: tuple[ReportSourceMessage, ...]
    versions: list[ReportVersion]
    current_version: int
    created_at: float
    updated_at: float

    @classmethod
    def create(
        cls,
        report_date: str,
        source_notes: str,
        source_session_id: str | None,
        source_chat_snapshot: Iterable[ReportSourceMessage],
        versions: Iterable[ReportVersion],
        current_version: int,
        created_at: float | None = None,
        updated_at: float | None = None,
    ) -> "DailyReport":
        date.fromisoformat(report_date)
        now = time.time()
        report = cls(
            date=report_date,
            source_notes=source_notes,
            source_session_id=source_session_id,
            source_chat_snapshot=tuple(source_chat_snapshot),
            versions=list(versions),
            current_version=current_version,
            created_at=created_at if created_at is not None else now,
            updated_at=updated_at if updated_at is not None else now,
        )
        numbers = [item.number for item in report.versions]
        if len(numbers) != len(set(numbers)):
            raise ReportValidationError("日报版本号不能重复")
        _ = report.current
        return report

    @property
    def current(self) -> ReportVersion:
        for version in self.versions:
            if version.number == self.current_version:
                return version
        raise ReportValidationError("当前日报版本不存在")
```

日期使用 `datetime.date.fromisoformat()` 严格验证；章节条目去除首尾空白并丢弃空字符串；对调用方列表做不可变复制。新增继承 `IrisError` 的 `ReportError`，再派生 `ReportNotFoundError`、`ReportValidationError`、`ReportStorageError`、`ReportGenerationError` 和 `ReportVersionConflictError`，每个错误带稳定 `code` 与安全中文消息。

- [ ] **步骤 4：补齐编解码和边界测试并运行**

覆盖无效日期、错误章节类型、空条目清理、版本号重复、当前版本不存在、来源角色限制。

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/reports/test_models.py -q`

预期：PASS。

- [ ] **步骤 5：提交任务 1**

```powershell
git add iris_agent/reports tests/reports/test_models.py
git commit -m "feat: add daily report domain models"
```

## 任务 2：本地 JSON 日报仓库

**文件：**
- 创建：`iris_agent/reports/repository.py`
- 测试：`tests/reports/test_repository.py`

- [ ] **步骤 1：编写仓库失败测试**

```python
def test_repository_round_trip_and_atomic_replace(tmp_path, monkeypatch):
    replaced = []
    monkeypatch.setattr(os, "replace", lambda src, dst: replaced.append((Path(src), Path(dst))))
    repository = JsonDailyReportRepository(tmp_path)
    repository.save(sample_report())
    assert replaced[0][0].parent == tmp_path
    assert replaced[0][1] == tmp_path / "2026-08-05.json"


def test_corrupt_report_is_not_overwritten(tmp_path):
    (tmp_path / "2026-08-05.json").write_text("{broken", encoding="utf-8")
    repository = JsonDailyReportRepository(tmp_path)
    with pytest.raises(ReportStorageError):
        repository.get("2026-08-05")
    assert (tmp_path / "2026-08-05.json").read_text(encoding="utf-8") == "{broken"
```

在同一测试文件实现 `sample_report()`：使用固定日期 `2026-08-05`、一个 `generated` 版本和 `ReportSections(completed=("完成日报设计",))` 调用 `DailyReport.create(report_date="2026-08-05", source_notes="记录", source_session_id=None, source_chat_snapshot=(), versions=(version,), current_version=1, created_at=1.0, updated_at=1.0)`，所有测试复用该确定样本。

- [ ] **步骤 2：运行测试确认仓库缺失**

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/reports/test_repository.py -q`

预期：FAIL，`JsonDailyReportRepository` 尚未定义。

- [ ] **步骤 3：实现仓库协议和原子存储**

```python
class DailyReportRepository(Protocol):
    def list(self) -> list[DailyReport]: ...
    def get(self, report_date: str) -> DailyReport: ...
    def save(self, report: DailyReport, expected_version: int | None = None) -> None: ...
    def report_lock(self, report_date: str) -> ContextManager[None]: ...
```

`JsonDailyReportRepository.__init__(directory: str | Path, max_versions: int = 20)` 创建目录、日期锁注册表和规范化根路径。

`save()` 在日期锁内重新读取磁盘当前版本并检查 `expected_version`；候选报告先复制并裁剪到最近 `max_versions`，序列化成功后才写入同目录临时文件，执行 `flush`、`os.fsync`、`os.replace`。保存失败清理临时文件但保留原异常链和原文件。

- [ ] **步骤 4：增加并发、失败和上限测试**

覆盖：不存在、无效日期、列表倒序、两线程同日版本冲突、不同日期互不阻塞、`json.dumps` 失败不改文件、`os.replace` 失败不改内存、最多 20 版本且保留当前版本。

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/reports/test_repository.py -q`

预期：PASS。

- [ ] **步骤 5：提交任务 2**

```powershell
git add iris_agent/reports/repository.py tests/reports/test_repository.py
git commit -m "feat: persist daily reports locally"
```

## 任务 3：提示词、模型输出解析与首次生成

**文件：**
- 创建：`iris_agent/reports/prompts.py`
- 创建：`iris_agent/reports/service.py`
- 测试：`tests/reports/test_service.py`

- [ ] **步骤 1：编写生成服务失败测试**

```python
def test_generate_uses_manual_notes_and_current_session(tmp_path):
    provider = FakeProvider(json.dumps(valid_sections(), ensure_ascii=False))
    sessions = JsonSessionRepository(tmp_path / "sessions")
    session = sessions.create("日报来源")
    sessions.append(session.id, Message(role="user", content="完成接口设计"))
    service = make_report_service(tmp_path, provider, sessions)

    report = service.generate("2026-08-05", "修复页面布局", session.id, include_chat=True)

    prompt = provider.calls[0][0][-1].content
    assert "修复页面布局" in prompt
    assert "完成接口设计" in prompt
    assert provider.calls[0][1] == []
    assert report.current.kind == "generated"
```

在测试文件中定义：`FakeProvider` 记录每次 `(messages, tools)` 并返回 `ProviderResponse(content=预设文本)`；`valid_sections()` 返回五个键且每个值均为字符串数组；`make_report_service()` 使用临时 `JsonDailyReportRepository` 组装服务。失败 Provider 单独抛 `RuntimeError("provider failed")`，测试只能断言安全的日报错误码，不能暴露该原文。

- [ ] **步骤 2：运行测试确认服务缺失**

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/reports/test_service.py -q`

预期：FAIL，`DailyReportService` 尚未定义。

- [ ] **步骤 3：实现固定提示词与严格 JSON 解析**

```python
SECTION_KEYS = ("completed", "in_progress", "problems", "next_day", "assistance")


def build_generate_messages(notes: str, chat: tuple[ReportSourceMessage, ...]) -> list[Message]:
    source = {
        "manual_notes": notes,
        "chat": [{"role": item.role, "content": item.content} for item in chat],
    }
    return [
        Message(role="system", content=GENERATION_SYSTEM_PROMPT),
        Message(role="user", content=json.dumps(source, ensure_ascii=False)),
    ]


def parse_model_sections(content: str) -> ReportSections:
    raw = json.loads(content)
    if not isinstance(raw, dict) or set(raw) != set(SECTION_KEYS):
        raise ReportGenerationError("report_model_output_invalid", "模型返回的日报格式无效")
    return ReportSections.from_mapping(raw)
```

不要从 Markdown 代码块或说明文字中猜测 JSON；模型不符合合约时失败关闭，不执行第二次模型请求。

- [ ] **步骤 4：实现 `DailyReportService.generate()`**

`DailyReportService.__init__(provider, sessions, repository, max_input_chars=50_000, max_revision_chars=2_000)` 保存依赖和限制。`generate(report_date: str, notes: str, session_id: str | None, include_chat: bool, expected_version: int | None = None) -> DailyReport` 完成验证、会话快照、模型调用、解析和原子保存。

仅复制 `user`/`assistant` 且 `content.strip()` 非空的消息；`include_chat=True` 但没有 `session_id` 时抛 `report_session_required`；模型异常包装为 `report_generation_failed`；成功前不保存任何部分结果。

- [ ] **步骤 5：补齐失败路径并运行测试**

覆盖：50,001 字拒绝、其他会话不导入、工具/系统消息过滤、缺会话 ID、未知会话、模型抛错、无效 JSON、缺字段、额外字段、错误数组类型、同日报重新生成形成新版本。

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/reports/test_service.py -q`

预期：PASS。

- [ ] **步骤 6：提交任务 3**

```powershell
git add iris_agent/reports/prompts.py iris_agent/reports/service.py tests/reports/test_service.py
git commit -m "feat: generate structured daily reports"
```

## 任务 4：手动保存、AI 修改、恢复和 Markdown

**文件：**
- 修改：`iris_agent/reports/prompts.py`
- 修改：`iris_agent/reports/service.py`
- 修改：`tests/reports/test_service.py`

- [ ] **步骤 1：编写版本操作失败测试**

```python
def test_failed_revision_keeps_current_version(report_service, repository, failing_provider):
    original = report_service.generate("2026-08-05", "记录", None, False)
    with pytest.raises(ReportGenerationError):
        report_service.revise("2026-08-05", "突出成果", original.current_version)
    assert repository.get("2026-08-05").current_version == original.current_version


def test_restore_creates_new_version(report_service):
    report = seeded_report_with_two_versions(report_service)
    restored = report_service.restore(report.date, 1, report.current_version)
    assert restored.current.kind == "restored"
    assert restored.current.sections == report.versions[0].sections
    assert len(restored.versions) == 3
```

`seeded_report_with_two_versions()` 先调用 `generate()`，再调用 `save_manual()` 创建第二版本并返回仓库中的日报；不要直接篡改仓库 JSON。

- [ ] **步骤 2：运行新增测试确认方法缺失**

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/reports/test_service.py -q`

预期：FAIL，`save_manual`、`revise`、`restore`、`render_markdown` 尚未定义。

- [ ] **步骤 3：实现版本操作**

增加四个精确方法：`save_manual(report_date: str, sections: ReportSections, expected_version: int) -> DailyReport`、`revise(report_date: str, instruction: str, expected_version: int) -> DailyReport`、`restore(report_date: str, version: int, expected_version: int) -> DailyReport`、`render_markdown(report_date: str, version: int | None = None) -> str`。

手动保存创建 `manual` 版本；AI 修改要求去空白后 1–2,000 字，提示词包含当前结构化章节；恢复只读取目标版本并创建新版本；所有写操作使用同日报锁和 `expected_version`；版本号严格递增。

- [ ] **步骤 4：实现固定 Markdown 渲染并测试**

Markdown 固定顺序如下，空章节仍保留并显示 `- 无`：

```markdown
# 2026 年 8 月 5 日工作日报

## 今日完成
- 完成日报设计

## 进行中
- 无
```

覆盖中文日期、五章节顺序、Markdown 特殊字符按普通文本保留、末尾单换行、指定旧版本下载。

- [ ] **步骤 5：运行服务与全量后端测试**

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/reports -q`

预期：PASS。

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest -q`

预期：全部 PASS，仅允许已有的 Starlette 弃用警告。

- [ ] **步骤 6：提交任务 4**

```powershell
git add iris_agent/reports tests/reports/test_service.py
git commit -m "feat: edit and version daily reports"
```

## 任务 5：配置与依赖组装

**文件：**
- 修改：`iris_agent/config/settings.py`
- 修改：`agent.yaml`
- 修改：`iris_agent/bootstrap.py`
- 修改：`server.py`
- 修改：`iris_agent/cli.py`
- 修改：`tests/config/test_settings.py`
- 测试：`tests/test_bootstrap.py`

- [ ] **步骤 1：编写配置和组装失败测试**

```python
def test_report_settings_defaults(tmp_path):
    settings = load_settings(tmp_path / "missing.yaml")
    assert settings.reports.directory == Path("data/reports")
    assert settings.reports.max_input_chars == 50_000
    assert settings.reports.max_versions == 20


def test_build_application_exposes_report_service(config_file, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    app = build_application(config_file)
    assert isinstance(app.reports, DailyReportService)
```

- [ ] **步骤 2：运行测试确认配置缺失**

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/config/test_settings.py tests/test_bootstrap.py -q`

预期：FAIL，`ReportSettings` 与应用容器尚未定义。

- [ ] **步骤 3：增加配置与 `ApplicationServices`**

```python
@dataclass(slots=True)
class ReportSettings:
    directory: Path = Path("data/reports")
    max_input_chars: int = 50_000
    max_revision_chars: int = 2_000
    max_versions: int = 20


@dataclass(frozen=True, slots=True)
class ApplicationServices:
    agent: AgentService
    sessions: SessionRepository
    reports: DailyReportService
    settings: Settings
```

`build_application()` 返回 `ApplicationServices`，CLI 使用 `application.agent/sessions`，Server 使用 `application.agent/sessions/reports`。验证所有数值大于 0，配置错误使用现有 `ConfigurationError`。

- [ ] **步骤 4：更新 `agent.yaml` 并运行回归测试**

```yaml
reports:
  directory: data/reports
  max_input_chars: 50000
  max_revision_chars: 2000
  max_versions: 20
```

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/config tests/test_bootstrap.py -q`

预期：PASS。

- [ ] **步骤 5：提交任务 5**

```powershell
git add iris_agent/config/settings.py agent.yaml iris_agent/bootstrap.py server.py iris_agent/cli.py tests/config/test_settings.py tests/test_bootstrap.py
git commit -m "feat: configure daily report service"
```

## 任务 6：FastAPI 日报接口

**文件：**
- 创建：`iris_agent/api/report_schemas.py`
- 修改：`iris_agent/api/app.py`
- 创建：`tests/api/test_reports.py`
- 修改：`tests/api/test_app.py`

- [ ] **步骤 1：编写 HTTP 合约失败测试**

```python
def test_generate_and_download_report(client, session_id):
    response = client.post("/api/reports/generate", json={
        "date": "2026-08-05",
        "notes": "完成日报接口",
        "include_chat": True,
        "session_id": session_id,
        "expected_version": None,
    })
    assert response.status_code == 201
    assert response.json()["current"]["kind"] == "generated"

    download = client.get("/api/reports/2026-08-05/download")
    assert download.headers["content-type"].startswith("text/markdown")
    assert "2026-08-05" in download.headers["content-disposition"]
```

`client` fixture 使用临时会话仓库、临时日报仓库和返回有效五章节 JSON 的 FakeProvider 创建 `DailyReportService`，再调用 `create_app(agent_service, sessions, report_service)`；`session_id` fixture 通过会话 API 创建当前会话。

- [ ] **步骤 2：运行测试确认接口为 404**

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/api/test_reports.py -q`

预期：FAIL，接口返回 404。

- [ ] **步骤 3：实现 Pydantic Schema 和路由**

`create_app(service, sessions, reports: DailyReportService | None = None)` 保持现有测试兼容；传入 `reports` 时注册全部日报路由。使用 `ReportSectionsSchema`、`GenerateReportRequest`、`SaveReportRequest`、`ReviseReportRequest` 和统一响应转换函数。生成返回 201，其余成功写操作返回 200。

- [ ] **步骤 4：映射稳定错误码和状态码**

映射规则：

- `report_not_found` → 404
- `report_invalid_date`、`report_input_too_long`、`report_session_required`、`report_model_output_invalid` → 422
- `report_version_conflict` → 409
- `report_generation_failed`、`report_storage_error` → 500

验证错误仍为 `{ "detail": { "code", "message" } }`，不返回异常详情。

- [ ] **步骤 5：补齐全部接口测试**

覆盖列表、单日、指定版本、生成、手动保存、AI 修改、恢复、下载、无效日期、输入超限、未知日报、版本冲突、模型失败和保存失败。现有 `tests/api/test_app.py` 必须继续通过。

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/api -q`

预期：PASS。

- [ ] **步骤 6：提交任务 6**

```powershell
git add iris_agent/api tests/api server.py
git commit -m "feat: expose daily report API"
```

## 任务 7：前端日报类型、API 和导航

**文件：**
- 修改：`web-react/package.json`
- 修改：`web-react/vite.config.ts`
- 创建：`web-react/src/test/setup.ts`
- 修改：`web-react/src/types.ts`
- 创建：`web-react/src/api/reports.ts`
- 修改：`web-react/src/App.tsx`
- 修改：`web-react/src/components/Sidebar.tsx`

- [ ] **步骤 1：安装最小测试依赖并增加脚本**

运行：`npm install -D vitest jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event`

在 `package.json` 增加：

```json
"test": "vitest run"
```

在 `vite.config.ts` 增加 `test: { environment: "jsdom", setupFiles: ["./src/test/setup.ts"] }`。

- [ ] **步骤 2：定义日报 TypeScript 类型**

```typescript
export type ReportSections = {
  completed: string[];
  in_progress: string[];
  problems: string[];
  next_day: string[];
  assistance: string[];
};

export type DailyReport = {
  date: string;
  current_version: number;
  current: ReportVersion;
  versions: ReportVersionSummary[];
  source_notes: string;
  source_session_id: string | null;
  updated_at: number;
};
```

- [ ] **步骤 3：实现严格 HTTP 客户端**

```typescript
export async function generateReport(input: GenerateReportInput): Promise<DailyReport> {
  return requestJson('/api/reports/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
}
```

集中解析 `{detail:{code,message}}` 为 `ReportApiError`；实现 list/get/generate/save/revise/restore 和 `downloadReportUrl(date)`。

- [ ] **步骤 4：增加聊天/日报导航状态**

`App` 定义 `type AppView = 'chat' | 'reports'`，从 `localStorage.getItem('iris_active_view')` 初始化并持久化。`Sidebar` 增加两个一级入口；点击日报不创建或删除聊天会话，切回聊天恢复原会话状态。

- [ ] **步骤 5：运行静态检查**

运行：`npm run lint`

预期：PASS。

运行：`npm run build`

预期：PASS。

- [ ] **步骤 6：提交任务 7**

```powershell
git add web-react/package.json web-react/package-lock.json web-react/vite.config.ts web-react/src/test web-react/src/types.ts web-react/src/api/reports.ts web-react/src/App.tsx web-react/src/components/Sidebar.tsx
git commit -m "feat: add daily report navigation and API client"
```

## 任务 8：日报 Hook、三栏组件与响应式布局

**文件：**
- 创建：`web-react/src/hooks/useDailyReports.ts`
- 创建：`web-react/src/hooks/useDailyReports.test.tsx`
- 创建：`web-react/src/components/reports/DailyReportPage.tsx`
- 创建：`web-react/src/components/reports/ReportHistory.tsx`
- 创建：`web-react/src/components/reports/ReportSourceEditor.tsx`
- 创建：`web-react/src/components/reports/ReportPreview.tsx`
- 创建：`web-react/src/components/reports/ReportRevisionBox.tsx`
- 创建：`web-react/src/components/reports/DailyReportPage.test.tsx`
- 修改：`web-react/src/App.tsx`
- 修改：`web-react/src/App.css`

- [ ] **步骤 1：编写 Hook 失败测试**

```tsx
it('debounces manual saves and keeps local text when save fails', async () => {
  vi.useFakeTimers();
  server.save.mockRejectedValue(new ReportApiError('report_storage_error', '保存失败'));
  const { result } = renderHook(() => useDailyReports({ currentSessionId: 'session_1' }));

  act(() => result.current.updateSection('completed', ['完成页面']));
  await act(() => vi.advanceTimersByTimeAsync(600));

  expect(result.current.draftSections.completed).toEqual(['完成页面']);
  expect(result.current.saveState).toBe('error');
});
```

- [ ] **步骤 2：运行测试确认 Hook 缺失**

运行：`npm test -- useDailyReports`

预期：FAIL，模块尚未创建。

- [ ] **步骤 3：实现 `useDailyReports` 状态机**

公开状态和操作：

```typescript
type SaveState = 'idle' | 'dirty' | 'saving' | 'saved' | 'error';

return {
  reports, selectedDate, report, draftSections, sourceNotes, includeChat,
  activeMobilePane, saveState, busyAction, error,
  selectDate, setSourceNotes, setIncludeChat, generate, updateSection,
  revise, restore, retrySave, copyMarkdown, downloadUrl, setActiveMobilePane,
};
```

使用 `useRef` 保存最新请求序号，忽略切换日期后的过期响应；自动保存使用 600 ms timeout 并在卸载时清理；版本冲突时停止自动重试，重新加载服务端版本并提示用户。

- [ ] **步骤 4：补齐 Hook 测试**

覆盖首次加载、日期切换、生成防重复、导入聊天缺会话提示、600 ms 防抖、保存失败保留草稿、重试、版本冲突、AI 修改失败、恢复、过期响应忽略。

运行：`npm test -- useDailyReports`

预期：PASS。

- [ ] **步骤 5：编写页面交互失败测试**

```tsx
it('generates a report and exposes copy, download, and revision controls', async () => {
  render(<DailyReportPage currentSessionId="session_1" />);
  await user.type(screen.getByLabelText('今日工作记录'), '完成日报页面');
  await user.click(screen.getByRole('button', { name: '生成汇报版日报' }));
  expect(await screen.findByText('今日完成')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '复制' })).toBeEnabled();
  expect(screen.getByRole('link', { name: '下载 .md' })).toHaveAttribute('href');
});
```

- [ ] **步骤 6：实现专注组件和三栏容器**

`DailyReportPage` 只组合 Hook 与子组件；`ReportHistory` 不请求 API；`ReportPreview` 用五组可编辑条目并提供增删条目；所有模型内容通过 React 文本节点渲染，不使用 `dangerouslySetInnerHTML`。

- [ ] **步骤 7：实现桌面三栏和窄屏标签**

CSS 使用：

```css
.report-workspace {
  display: grid;
  grid-template-columns: minmax(180px, 20%) minmax(280px, 32%) minmax(360px, 48%);
  height: 100vh;
}

@media (max-width: 960px) {
  .report-workspace { display: block; }
  .report-pane:not(.active) { display: none; }
  .report-mobile-tabs { display: flex; }
}
```

历史、来源和预览各自滚动；操作栏保持可见；现有聊天消息轨道和气泡样式不得改变。

- [ ] **步骤 8：运行前端测试与构建**

运行：`npm test`

预期：PASS。

运行：`npm run lint`

预期：PASS。

运行：`npm run build`

预期：PASS。

- [ ] **步骤 9：提交任务 8**

```powershell
git add web-react/src/hooks/useDailyReports.ts web-react/src/hooks/useDailyReports.test.tsx web-react/src/components/reports web-react/src/App.tsx web-react/src/App.css
git commit -m "feat: build daily report workspace"
```

## 任务 9：集成、文档和验收

**文件：**
- 创建：`tests/integration/test_daily_report_flow.py`
- 修改：`README.md`

- [ ] **步骤 1：编写完整集成测试**

```python
def test_daily_report_flow_from_chat_to_restored_markdown(application, client):
    session_id = create_chat_with_work_notes(client)
    generated = client.post("/api/reports/generate", json=generate_payload(session_id)).json()
    revised = client.post(
        "/api/reports/2026-08-05/revise",
        json={"instruction": "突出成果", "expected_version": generated["current_version"]},
    ).json()
    restored = client.post(
        "/api/reports/2026-08-05/versions/1/restore",
        json={"expected_version": revised["current_version"]},
    ).json()
    markdown = client.get("/api/reports/2026-08-05/download").text
    assert restored["current"]["kind"] == "restored"
    assert "## 今日完成" in markdown
```

集成测试中的 `create_chat_with_work_notes()` 通过真实会话 API 和聊天流写入一条用户工作记录；`generate_payload()` 返回固定日期、手动记录、`include_chat=True`、传入会话 ID 和空 `expected_version`。模型仍使用可编程 FakeProvider，不访问真实网络。

- [ ] **步骤 2：运行集成测试并修复接口接缝**

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest tests/integration/test_daily_report_flow.py -q`

预期：PASS。

- [ ] **步骤 3：更新 README**

增加：启动后进入日报页面、手动记录、导入当前对话、生成/修改/恢复、复制/下载、本地目录 `data/reports/`、20 版本限制、50,000 字限制、数据不会自动联网或执行工具。

- [ ] **步骤 4：执行后端最终验证**

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m pytest -q`

预期：全部 PASS，无新增非预期警告。

运行：`D:\agent\iris-agent\.venv\Scripts\python.exe -m compileall -q iris_agent iris_agent.py server.py`

预期：退出码 0。

- [ ] **步骤 5：执行前端最终验证**

在 `web-react` 运行：`npm test`

预期：PASS。

在 `web-react` 运行：`npm run lint`

预期：退出码 0。

在 `web-react` 运行：`npm run build`

预期：退出码 0，并生成 `dist/`。

- [ ] **步骤 6：运行质量检查和敏感信息检查**

运行：`git diff --check main...HEAD`

预期：无输出。

运行：`rg -n "(sk-|api[_-]?key|token|password)\s*[:=]\s*['\"][^'\"]+" --glob '!package-lock.json' --glob '!docs/**' .`

预期：没有真实密钥；测试占位值必须明显标为 `test-key` 或 `fake-token`。

- [ ] **步骤 7：手工浏览器验收**

使用 `start.cmd` 启动前后端并验证：

1. 在聊天页创建含工作记录的会话。
2. 切换日报页，填写手动记录并勾选导入当前对话。
3. 生成后五章节格式正确。
4. 手动编辑并等待“已保存”。
5. 用“更简短，突出成果”进行 AI 修改。
6. 刷新页面后内容仍存在。
7. 恢复旧版本后产生新版本。
8. 复制内容和下载的 Markdown 一致。
9. 将窗口缩窄到 960 px 以下，历史/记录/预览标签可切换。

- [ ] **步骤 8：提交任务 9**

```powershell
git add tests/integration/test_daily_report_flow.py README.md
git commit -m "docs: document daily report workflow"
```

---

## 实施约束

- 每项生产行为必须先看到对应测试因功能缺失而失败。
- 不合并或继续扩展暂停的 `feature/tool-approval-v02` 分支。
- 不新增 Word/PDF、定时任务、联网热点、UML、账号或数据库。
- 日报生成调用 `ModelProvider.complete(messages, tools=[])`，不得进入工具循环。
- 服务端只接受日期，不接受客户端文件路径。
- 模型输出校验失败、保存失败或版本冲突时不得覆盖当前日报。
- 前端不得使用 `dangerouslySetInnerHTML` 展示日报内容。
- 每个任务完成后运行对应专项测试并提交小粒度 commit。
- 完成前必须执行独立代码审查并修复全部 Critical/Important 问题。
