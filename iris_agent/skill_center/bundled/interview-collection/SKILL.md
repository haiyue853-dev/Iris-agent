---
id: interview-collection
name: 面试经验采集
description: 搜索公开面试资料，仅提取有明确答案的问答并保存到本地复习知识库。
icon: book-open
category: learning
entry_view: chat
version: 1
---
# 面试经验采集

使用 Interview Web MCP 完成以下流程：

1. 用 `search_interview_sources` 搜索主题。
2. 用 `extract_interview_qa` 逐页提取问答。
3. 仅保留完整的 question 和 answer，跳过介绍、目录、广告和无答案内容。
4. 等待用户审批 `save_interview_qa` 后保存，并报告新增数量与来源。
