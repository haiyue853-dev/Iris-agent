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

当用户要求收集某个方向的面试经验时：

1. 使用 `mcp__builtin-interview-web__search_interview_sources` 搜索主题。
2. 对候选来源使用 `mcp__builtin-interview-web__extract_interview_qa`。
3. 仅保留完整的 `question` 和 `answer`，忽略文章介绍、目录、广告和无答案内容。
4. 经用户确认保存操作后，使用 `mcp__builtin-interview-web__save_interview_qa` 保存，说明新增条数与来源。
