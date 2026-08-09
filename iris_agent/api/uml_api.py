"""UML 流程图生成 API。

复用 iris-agent 现有 LLM provider（设置界面配置的 API Key/模型），
根据用户的需求描述或代码生成 Mermaid 流程图源码。
"""

import logging
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from iris_agent.core.errors import ProviderError
from iris_agent.core.models import Message

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个专业的 UML 建模专家。根据用户提供的需求描述或代码，生成对应类型的 Mermaid 图。

通用要求：
1. 只输出一个 ```mermaid 代码块，不要输出任何解释文字
2. 节点文字使用简洁准确的中文（代码标识符可保留英文）
3. 语法必须正确，保证能在 Mermaid 中直接渲染
4. 节点数量控制在 5~15 个，突出主干，避免冗余
5. 【最重要】严格按 UML 符号规范标注节点形状（所有图形类图都适用）：
   - 开始/结束节点：圆角矩形 (...) 或圆形 ((...))
   - 处理/动作节点：矩形 [...]
   - 判断/决策节点：菱形 {...}
   - 输入/输出节点：平行四边形 [/.../]
   - 数据存储：圆柱 [(...)]
   - 预定义/子流程：双竖线 [[...]]
   不要把所有节点都画成矩形——不同语义用不同形状"""

DIAGRAM_HINTS = {
    "flowchart": "使用 flowchart TD/LR。严格按 UML 形状：开始/结束 ((...)) 或 (...)，处理 [...]，判断 {...}，输入输出 [/.../]，数据存储 [(...)]。",
    "activity": "活动图使用 flowchart 语法表达（可带 subgraph 泳道）。严格按 UML：开始/结束 ((...)) 或 (...)，动作/活动 [...]，判断 {...}，并发分支用 &。",
    "usecase": "用例图使用 flowchart 语法表达：参与者与用例均用圆形/椭圆 ((...))，include/extend 关系在连线上标注（如 -->|include|），系统边界用 subgraph 包裹。",
    "sequenceDiagram": "使用 sequenceDiagram，表达参与者之间的时序消息交互，激活/返回用 ->/-->>。",
    "classDiagram": "使用 classDiagram，表达类、属性、方法与关系：继承 <|--、实现 <|..、聚合 o--、组合 *--、关联 -->。",
    "erDiagram": "使用 erDiagram，表达实体（矩形）、属性（PK 主键 / FK 外键 标注）与关系（crow's foot 符号：||--o{、}|--|{、}o--o{ 等）。",
}

# 常见 mermaid 图类型的起始关键字，用于无代码块时兜底提取
_MERMAID_STARTS = (
    "flowchart", "graph", "sequenceDiagram", "classDiagram",
    "stateDiagram", "stateDiagram-v2", "erDiagram", "mindmap", "journey",
    "gantt", "pie", "gitGraph", "timeline", "block-beta",
)


class UmlAnalyzeRequest(BaseModel):
    prompt: str = Field(default="", max_length=20000, description="需求描述或代码内容")
    diagram_type: str = Field(
        default="flowchart",
        description="flowchart / activity / usecase / sequenceDiagram / classDiagram / erDiagram",
    )


def _extract_mermaid(text: str) -> str:
    """从 LLM 输出中提取 mermaid 代码块；无代码块时尝试按图类型关键字兜底。"""
    m = re.search(r"```(?:mermaid)?\s*\n?(.*?)```", text, re.S)
    if m and m.group(1).strip():
        return m.group(1).strip()
    # 兜底：找到图类型起始关键字，取其后全部内容
    m = re.search(r"((?:" + "|".join(_MERMAID_STARTS) + r")\b[\s\S]*)", text)
    if m:
        return m.group(1).strip()
    return ""


def register_uml_routes(app, service):
    """在 create_app 中注册流程图生成路由（需要访问运行中的 service 以复用 LLM provider）。"""

    @app.post("/api/uml/analyze")
    def analyze_uml(request: UmlAnalyzeRequest):
        prompt = request.prompt.strip()
        if not prompt:
            raise HTTPException(status_code=400, detail={"code": "empty_prompt", "message": "请输入需求描述或代码"})
        diagram_type = request.diagram_type if request.diagram_type in DIAGRAM_HINTS else "flowchart"
        hint = DIAGRAM_HINTS[diagram_type]

        provider = service.loop.provider
        messages = [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(role="user", content=f"请将以下内容绘制为 {diagram_type} 图。{hint}\n\n内容：\n{prompt}"),
        ]
        try:
            response = provider.complete(messages, [])
        except ProviderError as exc:
            logger.exception("流程图生成调用 LLM 失败")
            raise HTTPException(status_code=502, detail={"code": "llm_error", "message": "模型调用失败，请检查设置中的 API Key / 模型配置"}) from exc

        mermaid_code = _extract_mermaid(response.content)
        if not mermaid_code:
            mermaid_code = response.content.strip()
        return {"mermaid": mermaid_code, "raw": response.content}
