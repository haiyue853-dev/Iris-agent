---
id: interview-collection
name: 面试经验采集
description: 搜索公开面试资料，仅提取有明确答案的问答并保存到本地复习知识库。
icon: book-open
category: learning
entry_view: chat
version: 2
---
# 面试经验采集

使用 Interview Web MCP 完成以下流程：

1. 用 `search_interview_sources` 搜索主题。
2. 用 `extract_interview_qa` 逐页提取问答。
3. 仅保留完整的 question 和 answer，跳过介绍、目录、广告和无答案内容。
4. 等待用户审批 `save_interview_qa` 后保存，并报告新增数量与来源。
5. 如果页面无法访问、提取结果为空或问答数量不足，改用另一个搜索结果；必要时用更具体的岗位或技术栈关键词重新搜索。
6. 不要用完全相同的参数重复调用失败工具；在最终答复中说明尝试过的来源与未能获取的原因。
