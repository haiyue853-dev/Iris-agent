# GPT-SoVITS 权重加载验证实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 使用已安装的 GPT-SoVITS v2Pro 整合包加载授权的高松灯 v2ProPlus 权重，并确认模型成功进入 CUDA 推理环境。

**架构：** GPT-SoVITS 作为独立本地进程运行，仅监听 `127.0.0.1:9880`。先由 `api_v2.py` 加载整合包默认模型，再通过官方权重切换端点加载 `D:\AI\gsd` 中的 GPT 与 SoVITS 权重；通过 HTTP 响应、进程日志与 GPU 状态交叉验证。

**技术栈：** Windows PowerShell、GPT-SoVITS `runtime\python.exe`、FastAPI、NVIDIA CUDA。

---

## 文件与进程边界

- 读取：`D:\AI\GPT-SoVITS-v2pro-20250604\GPT-SoVITS-v2pro-20250604\api_v2.py`
- 读取：`D:\AI\GPT-SoVITS-v2pro-20250604\GPT-SoVITS-v2pro-20250604\GPT_SoVITS\configs\tts_infer.yaml`
- 读取：`D:\AI\gsd\MyGO_高松灯_v2pp.ckpt`
- 读取：`D:\AI\gsd\MyGO_高松灯_v2pp.pth`
- 临时输出：`D:\AI\gpt-sovits-validation\api.stdout.log`
- 临时输出：`D:\AI\gpt-sovits-validation\api.stderr.log`
- 进程：`runtime\python.exe api_v2.py`，监听 `127.0.0.1:9880`

### 任务 1：加载前检查

- [ ] 检查 9880 端口未被占用，确认两个权重非空且路径可读。
- [ ] 使用 Windows Defender 对 `D:\AI\gsd` 执行自定义扫描；若发现威胁，停止加载。
- [ ] 运行整合包 Python 的 `torch.cuda.is_available()`，预期输出 `True` 和 RTX 4060 设备名。

### 任务 2：启动本地 API

- [ ] 使用隐藏窗口启动 `runtime\python.exe api_v2.py -a 127.0.0.1 -p 9880 -c GPT_SoVITS/configs/tts_infer.yaml`，将标准输出与错误输出写入验证目录。
- [ ] 请求 `http://127.0.0.1:9880/openapi.json`，预期 HTTP 200；若失败，读取错误日志并停止进程。

### 任务 3：加载授权权重

- [ ] 请求 `/set_gpt_weights` 加载 `D:\AI\gsd\MyGO_高松灯_v2pp.ckpt`，预期返回 `success`。
- [ ] 请求 `/set_sovits_weights` 加载 `D:\AI\gsd\MyGO_高松灯_v2pp.pth`，预期返回 `success`。
- [ ] 检查进程仍存活、日志无 traceback，并用 `nvidia-smi` 确认 Python 进程使用 GPU 显存。

### 任务 4：报告结果

- [ ] 记录 API 进程号、权重加载结果、GPU 显存占用和任何兼容性错误。
- [ ] 若加载成功，保持 API 在本机运行以便补充参考音频后进行 `/tts` 合成；若加载失败，停止失败进程并保留日志用于诊断。
