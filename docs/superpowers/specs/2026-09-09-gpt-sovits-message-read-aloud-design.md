# GPT-SoVITS 消息朗读设计

## 目标

为 Iris Agent 的每条助手回复增加独立的“语音朗读”按钮。用户点击按钮后，Iris 按需启动本地 GPT-SoVITS、加载已授权的高松灯 v2ProPlus 权重，将该条消息的自然语言正文合成为中文 WAV，并立即在浏览器中播放。

## 范围

本功能覆盖 Web 对话页面、Iris 后端 TTS 服务、GPT-SoVITS 子进程管理、音频缓存和本机配置。它不改变模型的文字回复流程，不自动播放，不训练或修改语音权重，也不将 GPT-SoVITS 暴露到局域网或公网。

## 用户体验

- 每条已完成的助手消息气泡下方显示“语音朗读”按钮。
- 点击后按钮依次显示“正在生成语音”和“正在朗读”。
- 生成完成后立即播放；播放中再次点击暂停，暂停后点击继续。
- 播放结束后按钮恢复为“语音朗读”，再次点击从头播放缓存音频。
- 同一时间只播放一条消息；开始播放另一条消息时暂停当前音频。
- 流式回复尚未完成时不显示可用的朗读按钮。
- 错误显示在按钮旁，不影响消息正文、复制、重新生成或其他聊天功能。

## 架构

### 后端组件

新增独立的 `iris_agent/tts` 包：

- `models.py`：TTS 请求结果和领域错误。
- `text.py`：将 Markdown 助手回复转换为适合朗读的纯文本。
- `process.py`：检测、按需启动和关闭 GPT-SoVITS 进程。
- `client.py`：调用 GPT-SoVITS 的权重切换及 `/tts` 端点。
- `service.py`：校验消息、串行化推理、缓存 WAV 并编排上述组件。
- `api.py`：注册 Iris 的消息朗读 HTTP 路由。

`TtsService` 通过会话仓储按 `session_id + message_id` 查找消息，只允许朗读已持久化的助手消息。前端不直接提交待朗读正文，避免客户端内容与会话内容不一致。

### 前端组件

新增 `VoiceReadButton`，由助手消息组件在正文与现有操作栏之间渲染。组件读取当前消息 ID，通过 `IrisChatContext` 获取当前会话 ID，并调用 TTS API。浏览器使用 Blob URL 播放响应 WAV；组件卸载时撤销 Blob URL。

页面级音频协调器保证同一时间只有一个 `HTMLAudioElement` 播放。开始新消息的朗读时，先暂停上一条；不会删除上一条已取得的 Blob，以便再次播放。

## 数据流

1. 用户点击某条助手消息下方的“语音朗读”。
2. 前端 POST `/api/tts/sessions/{session_id}/messages/{message_id}`。
3. 后端读取会话消息并确认角色是 `assistant`、内容非空且不超过 4,000 个清洗后字符。
4. 文本清洗移除代码围栏及代码内容、Markdown 链接地址、图片、表格结构符号、HTML 标签和引用编号，保留自然语言链接标题、标题、列表文字与标点。
5. 服务以清洗后文本和当前声音配置生成 SHA-256 缓存键；已存在有效 WAV 时直接返回。
6. 缓存未命中时，进程管理器检查 `127.0.0.1:9880/openapi.json`。若不可用，则使用整合包自带 Python 以隐藏窗口启动 `api_v2.py`，最长等待 90 秒。
7. 每个 Iris 后端生命周期中首次连接 GPT-SoVITS 时，客户端依次调用 `/set_gpt_weights` 与 `/set_sovits_weights`，确保活动权重是配置的高松灯模型。
8. 服务以日语参考音频和参考文本调用 `/tts`：`prompt_lang=ja`、`text_lang=zh`、`media_type=wav`、`streaming_mode=false`。
9. 后端验证 HTTP 状态、`audio/*` 媒体类型、最大响应大小及 RIFF/WAVE 文件头，原子写入缓存后返回 WAV。
10. 前端创建 Blob URL 并立即播放。

## 进程生命周期与并发

- GPT-SoVITS 仅在第一次请求朗读且端口未提供健康服务时启动。
- 由 Iris 启动的进程在 Iris 应用关闭时终止；已由用户启动的进程只复用、不终止。
- 进程启动由单实例锁保护，多个首次请求不会启动多个进程。
- 推理由单实例锁串行执行，以避免 8 GB 显存上并发推理造成显存不足。
- 同一缓存键的并发请求共享最终缓存结果，不产生重复持久文件。

## 配置

在 `agent.yaml` 新增 `tts` 配置并由 `iris_agent.config.settings` 加载：

```yaml
tts:
  enabled: true
  provider: gpt_sovits
  base_url: http://127.0.0.1:9880
  root_directory: D:/AI/GPT-SoVITS-v2pro-20250604/GPT-SoVITS-v2pro-20250604
  gpt_weights_path: D:/AI/gsd/MyGO_高松灯_v2pp.ckpt
  sovits_weights_path: D:/AI/gsd/MyGO_高松灯_v2pp.pth
  reference_audio_path: D:/AI/KiraKsm/tomori/tomori_mp3/高松燈、です。よろしく…….mp3
  reference_text: 高松燈、です。よろしく……
  reference_language: ja
  target_language: zh
  cache_directory: data/tts
  startup_timeout_seconds: 90
  request_timeout_seconds: 300
  max_text_chars: 4000
  max_audio_bytes: 200000000
```

路径在启动时规范化和验证。配置关闭时路由返回明确的“语音朗读未启用”错误。模型与音频文件保留在 `D:\AI`，不复制到仓库或纳入 Git。

## API

`POST /api/tts/sessions/{session_id}/messages/{message_id}` 直接返回 `audio/wav`。成功响应包含：

- `Content-Type: audio/wav`
- `Cache-Control: private, max-age=31536000, immutable`
- `X-Iris-TTS-Cache: hit|miss`

错误统一为现有 FastAPI JSON 结构：

- `404`：会话或消息不存在。
- `409`：消息尚未完成或不是助手消息。
- `413`：清洗后正文超过 4,000 字或上游音频超过 200 MB。
- `503`：TTS 未启用、安装/权重/参考音频缺失、端口被非 GPT-SoVITS 服务占用。
- `504`：启动或推理超时。
- `502`：GPT-SoVITS 拒绝请求、返回非音频内容或无效 WAV。

所有错误面向用户提供简短中文信息，日志保留具体内部原因与路径。

## 缓存

缓存位于 `data/tts`，文件名只包含 SHA-256 摘要。缓存键包含：清洗后文本、权重路径、权重文件修改时间、参考音频路径及修改时间、参考文本、语言和推理参数。权重、参考音频或配置变化后会自然生成新缓存，不复用旧声音。

临时文件与最终 WAV 位于同一目录，写完并通过 WAV 校验后使用原子替换。失败请求清理自己的临时文件，不删除其他缓存。

## 测试与验收

### 后端自动化测试

- 配置加载、默认值、路径与数值校验。
- Markdown 清洗覆盖标题、列表、链接、代码块、HTML、图片和引用编号。
- 消息存在性、角色、空文本及 4,000 字限制。
- 健康服务复用、首次自动启动、并发启动去重、仅关闭自有进程。
- 权重切换顺序、日/中文语言参数、超时和上游错误映射。
- 缓存命中、配置变化失效、无效 WAV 不入缓存及原子写入。
- API 成功音频响应和所有错误状态。

### 前端自动化测试

- 仅已完成的助手消息显示按钮。
- 点击后的生成、播放、暂停、继续、结束和错误状态。
- 切换消息时暂停上一条音频。
- Blob URL 创建和组件卸载清理。

### 端到端验收

关闭现有 9880 服务并启动 Iris，点击一条助手回复的“语音朗读”。验收标准为：Iris 自动启动 GPT-SoVITS、加载配置权重、返回有效中文 WAV、浏览器开始播放；第二次点击同一消息时命中缓存且不再次推理；关闭 Iris 后由其启动的 GPT-SoVITS 进程退出。
